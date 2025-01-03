import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import pandas as pd
import json
import requests
import random
import plotly.express as px

from my_secrets import (
    DATAGOUV_API_KEY,
)
from tabs.utils import (
    bucket,
    folder,
    client,
    max_displayed_suggestions,
    get_file_content,
    get_latest_day_of_each_month,
    every_second_row_style,
)


suggestions_file = "suggestions.csv"


tab_certif = dcc.Tab(label="Certification", children=[
    dbc.Row([
        dbc.Col([
            dbc.Button(
                id='certif:button_refresh',
                children='Rafraîchir les données'
            ),
        ]),
        dcc.Graph(id="certif:graph"),
    ],
        style={"padding": "15px 0px 5px 0px"},
    ),
    dbc.Row([
        dbc.Col(id='certif:tooltip', children=[
            html.H3('Suggestions de certifications :'),
        ]),
        dbc.Tooltip(
            "Dans un souci de performances, seules "
            f"{max_displayed_suggestions} sont affichées. "
            "Une fois celles-ci traîtées, rafraîchir les données "
            "pour en afficher plus.",
            target="certif:tooltip",
            placement='right',
        ),
        dbc.Col([
            html.Div([
                dbc.Button(
                    id='certif:button_download',
                    children=(
                        'Télécharger les données des suggestions'
                    )
                ),
                dcc.Download(id="certif:download_stats")
            ]),
        ]),
    ]),
    html.Div(id='certif:suggestions'),
    dbc.Row(id='certif:issues'),
    dcc.Store(id='certif:datastore', data={}),
])


def is_certified(badges):
    for b in badges:
        if b['kind'] == 'certified':
            return True
    return False


def get_valid_domains(siret):
    if not siret:
        return set()
    r = requests.get(
        "https://tabular-api.data.gouv.fr/api/resources/4208f064-e655-4bad-93c9-9a3977f3f8cc/"
        f"data/?siret__exact={siret}&page_size=50"
    )
    r.raise_for_status()
    return set(d["domain_email"] for d in r.json()["data"])


def guess_valid_badge(siret):
    r = requests.get(
        "https://recherche-entreprises.api.gouv.fr/search?q=" + siret,
    ).json()["results"]
    if len(r) > 1:
        return None, "Plusieurs résultats pour ce SIRET : " + siret
    elif len(r) == 0:
        return None, "Aucun résultat pour ce SIRET : " + siret
    complements = r[0]['complements']
    if complements['collectivite_territoriale'] and complements['est_service_public']:
        return "local-authority", "Reconnu comme `SP` et `ColTer` => badge `ColTer`"
    elif complements['collectivite_territoriale']:
        return "local-authority", "Reconnu comme `collectivité territoriale`"
    elif complements['est_service_public']:
        return "public-service", "Reconnu comme `service public`"
    return None, "Ce message ne devrait jamais s'afficher, siret : " + siret


def certify_button(idx, orga_id, badge, current_badges):
    return dbc.Button(
        id={
            'type': 'certify',
            'index': f'certif:button_{idx}_{orga_id}_{badge}_{",".join(current_badges)}',
        },
        children=(
            f'Certifier cette organisation et appliquer le badge {badge}'
            if badge else "Pas d'action possible"
        ),
        color="info" if badge == "public-service" else "warning",
        disabled=badge is None,
    )


def create_certif_graph(stats):
    data = {
        'Mois': stats.keys(),
        'Orgas certifiées': [len(k['certified']) for k in stats.values()],
        'SP ou CT non certifiés': [
            len([o for o in k['SP_or_CT'] if o not in k['certified']])
            for k in stats.values()
        ],
    }
    df = pd.DataFrame(data)
    df = pd.melt(
        df,
        id_vars=['Mois'],
        var_name='Type',
        value_name='Nombre',
    )
    fig = px.bar(
        df,
        x='Mois',
        y='Nombre',
        color='Type',
        barmode='group',
        text_auto=True,
    )
    fig.update_layout(
        xaxis=dict(
            tickformat="%b 20%y",
        )
    )
    return fig


# %% Callbacks
@dash.callback(
    [
        Output("certif:graph", "figure"),
        Output("certif:suggestions", "children"),
        Output("certif:issues", "children"),
        Output("certif:datastore", "data"),
    ],
    [Input('certif:button_refresh', 'n_clicks')],
)
def refresh_certif(click):
    certif_dates = [
        f.object_name.replace(folder, '')[:-1]
        for f in client.list_objects(bucket, prefix=folder)
        if f.object_name.replace(folder, '').startswith('20')
    ]
    last_days = get_latest_day_of_each_month(certif_dates)
    stats = {}
    for idx, month in enumerate(last_days):
        stats[month] = {}
        for file in ['certified.json', 'SP_or_CT.json']:
            stats[month][file.replace('.json', '')] = json.loads(
                get_file_content(
                    last_days[month] + '/' + file
                )
            )
        if idx == len(last_days) - 1:
            issues = json.loads(get_file_content(
                last_days[month] + '/' + 'issues.json'
            ))
            certified = stats[month]['certified']
            SP_or_CT = stats[month]['SP_or_CT']

    session = requests.Session()
    suggestions = [
        o for o in SP_or_CT if o not in certified
    ]
    # to see more than just the first ones
    random.shuffle(suggestions)
    suggestions_divs = []
    suggestions_data = []

    for idx, orga_id in enumerate(suggestions):
        # for performance purposes, only displaying X suggestions
        # refresh when work is done to certify more
        if len(suggestions_divs) == max_displayed_suggestions:
            break
        params = session.get(
            f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/",
            headers={
                'X-fields': 'name,created_at,badges,members{user{email}},business_number_id',
                "X-API-KEY": DATAGOUV_API_KEY,
            }
        ).json()
        # to prevent showing orgas that have been certified since last DAG run
        if 'badges' not in params or is_certified(params['badges']):
            continue
        current_badges = [b["kind"] for b in params['badges']]
        emails = [u["user"]["email"] for u in params["members"]]
        valid_domains = get_valid_domains(params["business_number_id"])
        badge, text = guess_valid_badge(params["business_number_id"])
        present_domains = []
        for domain in valid_domains:
            if any(email.endswith("@" + domain) for email in emails):
                present_domains.append(domain)
        md = (
            f"- [{params['name']}]"
            f"(https://www.data.gouv.fr/fr/organizations/{orga_id}/)"
        )
        if current_badges:
            md += f", badge actuel : `{', '.join(current_badges)}`"
        if not emails:
            md += '\n   - Pas de membres dans cette organisation'
        for email in emails:
            md += '\n   - ' + email
        if present_domains:
            md += f"\n\n✅ Emails vérifiés: {', '.join(present_domains)}"
        suggestions_divs += [dbc.Row(children=[
            dbc.Col(children=[dcc.Markdown(md)]),
            dbc.Col(children=[
                html.Div(
                    certify_button(idx, orga_id, badge, current_badges),
                    style={"padding": "10px 0px 0px 0px"},
                ),
                dcc.Markdown(text)
            ]),
        ],
            style=every_second_row_style(idx),
        )]
        suggestions_data.append({
            'name': params['name'],
            'created_at': params['created_at'][:10],
            'url': f'https://www.data.gouv.fr/fr/organizations/{orga_id}/',
            'emails': '; '.join(emails),
        })

    issues_md = ''
    if issues:
        issues_md += '## Liste des SIRETs qui posent problème :'
    for i in issues:
        name = session.get(
            "https://www.data.gouv.fr/api/1/"
            f"organizations/{list(i.keys())[0]}/",
            headers={'X-fields': 'name'}
        )
        if name.ok:
            name = name.json()['name']
            issues_md += (
                f"\n- [{name}](https://www.data.gouv.fr/fr/organizations/"
                f"{list(i.keys())[0]}) : {list(i.values())[0]}"
            )

    return (
        create_certif_graph(stats),
        suggestions_divs,
        [dcc.Markdown(issues_md)],
        {"suggestions": suggestions_data},
    )


@dash.callback(
    Output("certif:suggestions", "children", allow_duplicate=True),
    [Input({'type': 'certify', 'index': dash.ALL}, 'n_clicks')],
    prevent_initial_call=True,
)
# this is triggered on click, we use context to get which button was clicked
# and perform the right action according to the button id
def update_after_certif(*args):
    patched_children = dash.Patch()
    if all([a is None for a in args[0]]):
        raise PreventUpdate
    # par construction, don't worry it works
    idx, orga_id, badge, current_badges = eval(
        dash.ctx.triggered[0]["prop_id"].split(".")[0]
    )['index'].split('_')[1:]
    idx = int(idx)
    current_badges = current_badges.split(",")
    to_add = [b for b in [badge, "certified"] if b not in current_badges]
    to_remove = [b for b in current_badges if b not in [badge, "certified"]]
    for b in to_remove:
        requests.delete(
            f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/badges/{b}/",
            headers={"X-API-KEY": DATAGOUV_API_KEY},
        )
    for b in to_add:
        r = requests.post(
            f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/badges/",
            json={"kind": b},
            headers={"X-API-KEY": DATAGOUV_API_KEY},
        )
        if not r.ok:
            patched_children[idx] = dbc.Row(children=[html.H4(
                'Une erreur est survenue '
                'en essayant de certifier [cette organisation]'
                f'(https://www.data.gouv.fr/fr/organizations/{orga_id}/)'
            )],
                style={'background-color': '#ffb6c1'},
            )
            return patched_children

    patched_children[idx] = dbc.Row(
        children=[dcc.Markdown(children=[
            f"[Organisation](https://www.data.gouv.fr/fr/organizations/{orga_id}/) certifiée ☑️"
        ])],
        style={'background-color': '#90ee90'},
    )
    return patched_children


@dash.callback(
    Output("certif:download_stats", "data"),
    [Input('certif:button_download', 'n_clicks')],
    [State('certif:datastore', 'data')],
    prevent_initial_call=True,
)
def download_data_certif(click, datastore):
    if click:
        df = pd.DataFrame(datastore['suggestions'])
        return {
            'content': df.to_csv(index=False),
            'filename': suggestions_file
        }
    return
