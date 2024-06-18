# -*- coding: utf-8 -*-

import dash
# from dash import dash_table
from dash import dcc
from dash import html
import dash_auth
# import dash_daq as daq
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
import requests
import re
from unidecode import unidecode
from minio import Minio
from thefuzz import fuzz
from io import StringIO
from time import sleep
import random
from my_secrets import (
    VALID_USERNAME_PASSWORD_PAIRS,
    DATAGOUV_API_KEY,
)
from maindash import app
from tabs.support import tab_support
from tabs.kpi_and_catalog import tab_kpi_catalog

bucket = "dataeng-open"
folder = "dashboard/"
suggestions_file = "suggestions.csv"
max_displayed_suggestions = 10
duplicate_slug_pattern = r'-\d+$'
entreprises_api_url = "https://recherche-entreprises.api.gouv.fr/search?q="
client = Minio(
    "object.files.data.gouv.fr",
    secure=True,
)

auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)

# %% Functions


def get_file_content(
    client,
    bucket,
    file_path,
    encoding="utf-8",
):
    r = client.get_object(bucket, file_path)
    return r.read().decode(encoding)


def get_latest_day_of_each_month(days_list):
    last_days = {}
    for day in sorted(days_list):
        month = day[:7]
        if month not in last_days:
            last_days[month] = day
        elif last_days[month] < day:
            last_days[month] = day
    return last_days


def every_second_row_style(idx):
    return {'background-color': 'lightgray' if idx % 2 == 0 else 'white'}


def is_certified(badges):
    for b in badges:
        if b['kind'] == 'certified':
            return True
    return False


def clean(text):
    if isinstance(text, str):
        if re.search(duplicate_slug_pattern, text) is not None:
            suffix = re.findall(duplicate_slug_pattern, text)[0]
            text = text[:-len(suffix)]
        return unidecode(text.lower()).replace('-', '')
    else:
        # print(text)
        return ""


def symetric_ratio(s1, s2):
    _score = fuzz.partial_ratio
    if len(s1) > len(s2):
        return _score(s2, s1)
    return _score(s1, s2)


def get_siret_from_siren(siren):
    try:
        r = requests.get(entreprises_api_url + siren)
    except:
        sleep(1)
        try:
            r = requests.get(entreprises_api_url + siren)
        except:
            return None
    if not r.ok:
        return None
    r = r.json()['results']
    if len(r) == 0:
        print('No result')
        return None
    if len(r) > 1:
        print("Ambiguous :", len(r))
        return None
    else:
        return r[0]['siege']['siret']


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


# %% APP LAYOUT:
app.layout = dbc.Container(
    [
        dbc.Row([
            html.H3(
                "Visualisation d'indicateurs de data.gouv.fr",
                style={
                    "padding": "5px 0px 10px 0px",
                    # "padding": "top right down left"
                },
            ),
        ]),
        dcc.Tabs([
            tab_support,
            tab_kpi_catalog,
            dcc.Tab(label="Reuses", children=[
                dbc.Row([
                    dbc.Button(
                        id='reuses:button_refresh',
                        children='Rafraîchir les données'
                    ),
                    dcc.Graph(id='reuses:graph'),
                ],
                    style={"padding": "15px 0px 5px 0px"},
                ),
            ]),
            dcc.Tab(label="Certification", children=[
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
                # html.H6(id='tmp_output'),
                html.Div(id='certif:suggestions'),
                dbc.Row(id='certif:issues'),
            ]),
            dcc.Tab(label="SIRETisation (IRVE)", children=[
                dbc.Row(children=[
                    dbc.Col(id='siret:tooltip', children=[
                        html.H3(
                            'Correspondances SIRETs trouvés dans les IRVE :'
                        ),
                    ], width=9),
                    dbc.Tooltip(
                        "Dans un souci de performances, seules "
                        f"{max_displayed_suggestions} sont affichées. "
                        "Une fois celles-ci traîtées, rafraîchir les données "
                        "pour en afficher plus.",
                        target="siret:tooltip",
                        placement='bottom',
                    ),
                    dbc.Col(children=[
                        dbc.Row(children=[
                            html.H6('Tolérance du matching'),
                            dcc.Slider(
                                min=0,
                                max=90,
                                step=10,
                                value=70,
                                id='siret:slider'
                            ),
                        ]),
                        dbc.Row(children=[
                            dbc.Button(
                                id='siret:button_refresh',
                                children=(
                                    'Rafraîchir les données'
                                )
                            ),
                        ]),
                    ], width=3),
                ],
                    style={"padding": "15px 0px 5px 0px"},
                ),
                html.Div(id='siret:matches'),
            ]),
        ]),
        dcc.Store(id='datastore', data={}),
        dcc.Store(id='certif:datastore', data={}),
    ])

# %% Callbacks


# Reuses
@app.callback(
    Output("reuses:graph", "figure"),
    [Input('reuses:button_refresh', 'n_clicks')],
)
def refresh_reuses_graph(click):
    hist = pd.read_csv(StringIO(
        get_file_content(client, bucket, folder + 'stats_reuses_down.csv')
    ))
    hist = hist.loc[hist['Date'].isin(
        get_latest_day_of_each_month(hist['Date']).values()
    )]
    hist['Date'] = hist['Date'].apply(lambda x: x[:7])
    scatter = hist.copy(deep=True)
    scatter['Taux'] = scatter.apply(
        lambda df: round(
            (df['404'] + df['Autre erreur']) / df['Total'] * 100,
            1
        ),
        axis=1
    )
    hist = hist[['Date', '404', 'Autre erreur']]
    fig = px.bar(
        pd.melt(
            hist,
            id_vars=['Date'],
            var_name='Type erreur',
            value_name='Nombre'
        ),
        x='Date',
        y='Nombre',
        color='Type erreur',
        title='Nombre de reuses qui renvoient une erreur',
        text_auto=True,
    )
    fig.update_layout(
        xaxis=dict(
            tickformat="%b 20%y",
            title="Mois",
        )
    )
    fig.add_trace(go.Scatter(
        x=scatter['Date'].to_list(),
        y=scatter['Taux'].to_list(),
        mode='lines',
        name='Taux de reuses down',
        yaxis='y2'
    ))
    fig.update_layout(
        yaxis2=dict(
            title='Taux de reuses down',
            overlaying='y',
            side='right',
            range=[0, max(scatter['Taux']) * 1.1]
        ),
        legend=dict(
            orientation='h',
            y=1.1,
            x=0
        )
    )
    return fig


# Certif
@app.callback(
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
                    client,
                    bucket,
                    folder + last_days[month] + '/' + file
                )
            )
        if idx == len(last_days) - 1:
            issues = json.loads(get_file_content(
                client,
                bucket,
                folder + last_days[month] + '/' + 'issues.json'
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

    for idx, s in enumerate(suggestions):
        # for performance purposes, only displaying X suggestions
        # refresh when work is done to certify more
        if len(suggestions_divs) == max_displayed_suggestions:
            break
        params = session.get(
            f"https://www.data.gouv.fr/api/1/organizations/{s}/",
            headers={
                'X-fields': 'name,created_at,badges,members{user{uri}}',
            }
        ).json()
        # to prevent showing orgas that have been certified since last DAG run
        if 'badges' not in params or is_certified(params['badges']):
            continue
        emails = []
        for user in params['members']:
            r = session.get(
                user['user']['uri'],
                headers={"X-API-KEY": DATAGOUV_API_KEY},
            ).json()
            emails.append(r['email'])
        md = (
            f"- [{params['name']}]"
            f"(https://www.data.gouv.fr/fr/organizations/{s}/)"
        )
        if not emails:
            md += '\n   - Pas de membres dans cette organisation'
        for email in emails:
            md += '\n   - ' + email
        suggestions_divs += [dbc.Row(children=[
            dbc.Col(children=[dcc.Markdown(md)]),
            dbc.Col(children=[html.Div(dbc.Button(
                id={
                    'type': 'certify',
                    'index': f'certif:button_{len(suggestions_divs)}_{s}'
                },
                children='Certifier cette organisation',
                color="info",
            ),
                style={"padding": "10px 0px 0px 0px"},
            )]),
        ],
            style=every_second_row_style(len(suggestions_divs)),
        )]
        suggestions_data.append({
            'name': params['name'],
            'created_at': params['created_at'][:10],
            'url': f'https://www.data.gouv.fr/fr/organizations/{s}/',
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


@app.callback(
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
    idx, orga_id = eval(
        dash.ctx.triggered[0]["prop_id"].split(".")[0]
    )['index'].split('_')[-2:]
    idx = int(idx)
    # r = requests.get(
    #     f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/",
    #     headers={'X-fields': 'name'},
    # )
    for badge in ["public-service", "certified"]:
        r = requests.post(
            f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/badges/",
            json={"kind": badge},
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

    r = requests.get(
        f"https://www.data.gouv.fr/api/1/organizations/{orga_id}/",
        headers={'X-fields': 'name'},
    ).json()
    patched_children[idx] = dbc.Row(
        children=[dcc.Markdown(children=[
            f"- [{r['name']}]"
            f"(https://www.data.gouv.fr/fr/organizations/{orga_id}/)"
            " : certifiée ☑"
        ])],
        style={'background-color': '#90ee90'},
    )
    return patched_children


@app.callback(
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


# SIRET
@app.callback(
    Output("siret:matches", "children"),
    [Input('siret:button_refresh', 'n_clicks')],
    [State('siret:slider', 'value')],
)
def refresh_siret(click, slider):
    df = pd.read_csv(
        'https://www.data.gouv.fr/fr/datasets/'
        'r/eb76d20a-8501-400e-b336-d85724de5435',
        dtype=str,
        usecols=[
            'nom_amenageur',
            'siren_amenageur',
            'datagouv_organization_or_owner',
        ]
    )
    restr = df.loc[
        (~df['siren_amenageur'].isna()) & (~df['nom_amenageur'].isna())
    ].drop_duplicates()
    restr['cleaned_nom'] = restr['nom_amenageur'].apply(clean)
    restr['cleaned_orga'] = restr['datagouv_organization_or_owner'].apply(
        clean
    )
    restr['ratio'] = restr.apply(
        lambda df_: symetric_ratio(df_['cleaned_orga'], df_['cleaned_nom']),
        axis=1
    )
    restr = restr.loc[restr['ratio'] > slider]
    siret_divs = []
    session = requests.Session()
    for orga in restr['datagouv_organization_or_owner'].unique():
        if len(siret_divs) == max_displayed_suggestions:
            break
        tmp = restr.loc[
            restr['datagouv_organization_or_owner'] == orga
        ].drop_duplicates('siren_amenageur')
        if len(tmp) == 1:
            siren = list(tmp['siren_amenageur'])[0]
            siret = get_siret_from_siren(siren)
            if not siret:
                continue
            slug = list(tmp['datagouv_organization_or_owner'])[0]
            r = session.get(
                f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
                headers={'X-fields': 'name,business_number_id'},
            ).json()
            if r['business_number_id']:
                # print(orga, 'already has siret:', r['business_number_id'])
                continue
            match = list(tmp['nom_amenageur'])[0]
            md1 = (
                f"[{r['name']}](https://www.data.gouv.fr/fr/{slug}/) "
                f"matchée avec {match}"
            )
            md2 = f"\nSIREN : {siren}, SIRET : {siret}"
            siret_divs += [dbc.Row(children=[
                dbc.Col(children=[dcc.Markdown(md1), dcc.Markdown(md2)]),
                dbc.Col(children=[html.Div(dbc.Button(
                    id={
                        'type': 'siret',
                        'index': f'siret:button_{len(siret_divs)}_{slug}_{siret}'
                    },
                    children='SIRETiser cette organisation',
                    color="info",
                ),
                    style={"padding": "10px 0px 0px 0px"},
                )]),
            ],
                style=every_second_row_style(len(siret_divs)),
            )]
    return siret_divs


@app.callback(
    Output("siret:matches", "children", allow_duplicate=True),
    [Input({'type': 'siret', 'index': dash.ALL}, 'n_clicks')],
    prevent_initial_call=True,
)
def update_after_siret(*args):
    patched_children = dash.Patch()
    if all([a is None for a in args[0]]):
        raise PreventUpdate
    # par construction, don't worry it works
    idx, slug, siret = eval(
        dash.ctx.triggered[0]["prop_id"].split(".")[0]
    )['index'].split('_')[-3:]
    idx = int(idx)
    # r = requests.get(
    #     f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
    #     headers={'X-fields': 'name'},
    # )
    r = requests.put(
        f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
        json={'business_number_id': siret},
        headers={"X-API-KEY": DATAGOUV_API_KEY},
    )
    if not r.ok:
        patched_children[idx] = dbc.Row(children=[html.H4(
            'Une erreur est survenue '
            'en essayant de SIRETiser [cette organisation]'
            f'(https://www.data.gouv.fr/fr/organizations/{slug}/)'
        )],
            style={'background-color': '#ffb6c1'},
        )
        return patched_children

    r = r.json()
    patched_children[idx] = dbc.Row(
        children=[dcc.Markdown(children=[
            f"[{r['name']}]"
            f"(https://www.data.gouv.fr/fr/organizations/{slug}/)"
            f" : siretisée avec {siret}"
        ])],
        style={'background-color': '#90ee90'},
    )
    return patched_children


# %%
if __name__ == '__main__':
    app.run_server(debug=False, use_reloader=False, port=8053)
