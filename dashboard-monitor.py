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
from minio import Minio
from my_secrets import (
    VALID_USERNAME_PASSWORD_PAIRS,
    DATAGOUV_API_KEY,
)

external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
bucket = "dataeng-open"
folder = "dashboard/"
support_file = "stats_support.csv"
suggestions_file = "suggestions.csv"
client = Minio(
    "object.files.data.gouv.fr",
    secure=True,
)

auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)


def get_latest_day_of_each_month(days_list):
    last_days = {}
    for day in days_list:
        month = day[:7]
        if month not in last_days:
            last_days[month] = day
        elif last_days[month] < day:
            last_days[month] = day
    return last_days


def is_certified(badges):
    for b in badges:
        if b['kind'] == 'certified':
            return True
    return False


def create_volumes_graph(stats):
    volumes = stats.copy()
    volumes.loc['Autre ticket'] = (
        volumes.loc['Ouverture de ticket'] - volumes.loc['Ticket hors-sujet']
    )
    volumes = volumes.T
    volumes.index.names = ['Date']
    volumes.reset_index(inplace=True)
    volumes = pd.melt(
        volumes,
        id_vars=['Date'],
        var_name='Page',
        value_name='Visites',
    )
    volumes = volumes.loc[
        volumes['Page'].isin(['Autre ticket', 'Ticket hors-sujet'])
    ].sort_values('Page')
    volumes.rename({"Visites": "Nombre de tickets"}, axis=1, inplace=True)
    fig = px.bar(
        volumes,
        x="Date",
        y="Nombre de tickets",
        color="Page",
        text_auto=True,
    )
    fig.add_trace(go.Scatter(
        x=stats.columns,
        y=stats.loc['Page support'],
        mode='lines',
        name='Nombre de visites sur le support',
        yaxis='y2'
    ))
    fig.update_layout(
        yaxis2=dict(
            title='Nombre de visites sur le support',
            overlaying='y',
            side='right',
            range=[0, max(stats.loc['Page support']) * 1.1]
        ),
        legend=dict(
            orientation='h',
            y=1.1,
            x=0
        )
    )
    return fig


def create_taux_graph(stats):
    conversions = pd.DataFrame(columns=stats.columns)
    for idx, level in enumerate(stats.index[:-1]):
        conversions.loc[f"{level} => {stats.index[idx+1]}"] = (
            round(stats.loc[stats.index[idx + 1]] / stats.loc[level], 3) * 100
        )
    transposed = conversions.T
    transposed.index.names = ['Date']
    transposed.reset_index(inplace=True)
    transposed = pd.melt(
        transposed,
        id_vars=['Date'],
        var_name='Taux de passage entre',
        value_name='Taux de passage',
    )
    fig = px.line(
        transposed,
        x='Date',
        y='Taux de passage',
        color='Taux de passage entre',
    )
    return fig


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
    )
    fig.update_layout(
        xaxis=dict(
            tickformat="%b 20%y",
            dtick="M1"
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
            dcc.Tab(label="Support", children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Button(
                            id='support:button_refresh',
                            children='Rafraîchir les données'
                        ),
                    ]),
                    dbc.Col([
                        html.Div([
                            dbc.Button(
                                id='support:button_download',
                                children='Télécharger les données sources'
                            ),
                            dcc.Download(id="support:download_stats")
                        ])
                    ]),
                    dcc.Graph(id="support:graph_taux"),
                    dcc.Graph(id="support:graph_volumes"),
                ],
                    style={"padding": "5px 0px 5px 0px"},
                ),
            ]),
            dcc.Tab(label="KPIs", children=[
                dbc.Row([
                    dbc.Col([
                        dcc.Dropdown(id="kpi:dropdown"),
                    ]),
                    dbc.Col([
                        dbc.Button(
                            id='kpi:button_refresh',
                            children='Rafraîchir les données'
                        ),
                    ]),
                ],
                    style={"padding": "5px 0px 5px 0px"},
                ),
                dcc.Graph(id='kpi:graph_kpi'),
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
                    style={"padding": "5px 0px 5px 0px"},
                ),
                dbc.Row([
                    dbc.Col([
                        html.H3('Suggestions de certifications :'),
                    ]),
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
                dbc.Row(id='certif:suggestions'),
                dbc.Row(id='certif:issues'),
            ]),
        ]),
        dcc.Store(id='datastore', data={}),
        dcc.Store(id='certif:datastore', data={}),
    ])

# %% Callbacks


# Support
@app.callback(
    [
        Output('support:graph_volumes', 'figure'),
        Output('support:graph_taux', 'figure'),
    ],
    [Input('support:button_refresh', 'n_clicks')]
)
def update_dropdown_options(click):
    client.fget_object(
        bucket, folder + support_file, support_file
    )
    stats = pd.read_csv(support_file, index_col=0)
    return create_volumes_graph(stats), create_taux_graph(stats)


@app.callback(
    Output("support:download_stats", "data"),
    [Input('support:button_download', 'n_clicks')]
)
def download_data_support(click):
    if click:
        stats = pd.read_csv(support_file, index_col=0)
        return {
            'content': stats.to_csv(),
            'filename': support_file
        }
    return


# KPIs
@app.callback(
    Output("datastore", "data"),
    [Input('kpi:button_refresh', 'n_clicks')],
    [State("datastore", "data")]
)
def refresh_kpis(click, datastore):
    kpis = pd.read_csv(
        'https://www.data.gouv.fr/fr/datasets/'
        'r/79e2c14d-8278-4407-84b5-e8c279fc578c'
    )
    datastore.update({'kpis': kpis.to_json()})
    return datastore


@app.callback(
    Output("kpi:dropdown", "options"),
    [Input('datastore', 'data')],
)
def refresh_kpis_dropdown(datastore):
    kpis = pd.read_json(datastore['kpis'])
    options = [
        {'label': k, 'value': k} for k in kpis['indicateur'].unique()
    ]
    return options


@app.callback(
    Output("kpi:graph_kpi", "figure"),
    [Input('kpi:dropdown', 'value')],
    [State("datastore", "data")]
)
def change_kpis_graph(indic, datastore):
    if not indic:
        raise PreventUpdate
    mapping = {
        'barchart': px.bar,
        'linechart': px.line,
        'scatterplot': px.scatter,
    }
    kpis = pd.read_json(datastore['kpis'])
    restr = kpis.loc[kpis['indicateur'] == indic].sort_values('date')
    restr['mois'] = restr['date'].apply(lambda d: d.strftime('%Y-%m'))
    restr = restr.drop_duplicates(subset='mois')
    _method = mapping.get(restr['dataviz_wish'].unique()[0])
    fig = _method(
        restr,
        x='mois',
        y='valeur',
        title=indic
    )
    fig.update_layout(
        xaxis=dict(
            title='Mois',
            tickformat="%b 20%y",
            dtick="M1"
        ),
        yaxis_title=f"Valeur ({restr['unite_mesure'].unique()[0]})",
        yaxis_range=[0, max(restr['valeur'])*1.1]
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
            client.fget_object(
                bucket, folder + last_days[month] + '/' + file, file
            )
            with open(file, 'r') as f:
                tmp = json.load(f)
            stats[month][file.replace('.json', '')] = tmp
        if idx == len(last_days) - 1:
            client.fget_object(
                bucket,
                folder + last_days[month] + '/' + 'issues.json',
                'issues.json'
            )
            with open('issues.json', 'r') as f:
                issues = json.load(f)
            with open('certified.json', 'r') as f:
                certified = json.load(f)
            with open('SP_or_CT.json', 'r') as f:
                SP_or_CT = json.load(f)

    session = requests.Session()
    suggestions = [
        o for o in SP_or_CT if o not in certified
    ]
    suggestions_md = ''
    suggestions_data = []
    for idx, s in enumerate(suggestions):
        params = session.get(
            f"https://www.data.gouv.fr/api/1/organizations/{s}/",
            headers={
                'X-fields': 'name,created_at,badges,members{user{uri}}',
            }
        ).json()
        # to prevent showing orgas that have been certified since last DAG run
        if is_certified(params['badges']):
            continue
        emails = []
        for user in params['members']:
            r = session.get(
                user['user']['uri'],
                headers={"X-API-KEY": DATAGOUV_API_KEY},
            ).json()
            emails.append(r['email'])
        if idx > 0:
            suggestions_md += '\n'
        suggestions_md += (
            f"- [{params['name']}]"
            f"(https://www.data.gouv.fr/fr/organizations/{s}/)"
        )
        for email in emails:
            suggestions_md += '\n   - ' + email
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
        ).json()['name']
        issues_md += (
            f"\n- [{name}](https://www.data.gouv.fr/fr/organizations/"
            f"{list(i.keys())[0]}) : {list(i.values())[0]}"
        )

    return (
        create_certif_graph(stats),
        [dcc.Markdown(suggestions_md)],
        [dcc.Markdown(issues_md)],
        {"suggestions": suggestions_data},
    )


@app.callback(
    Output("certif:download_stats", "data"),
    [Input('certif:button_download', 'n_clicks')],
    [State('certif:datastore', 'data')],
)
def download_data_certif(click, datastore):
    if click:
        df = pd.DataFrame(datastore['suggestions'])
        return {
            'content': df.to_csv(index=False),
            'filename': suggestions_file
        }
    return


# %%
if __name__ == '__main__':
    app.run_server(debug=False, use_reloader=False, port=8053)
