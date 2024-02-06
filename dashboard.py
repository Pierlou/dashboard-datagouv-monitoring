# -*- coding: utf-8 -*-

import dash
# from dash import dash_table
from dash import dcc
from dash import html
# import dash_daq as daq
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from minio import Minio

external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
bucket = "dataeng-open"
path = "support/stats_support.csv"
client = Minio(
    "object.files.data.gouv.fr",
    secure=True,
)


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


# %% APP LAYOUT:
app.layout = dbc.Container(
    [
        dbc.Row([
            html.H3(
                "Visualisation d'indicateurs de data.gouv.fr",
                style={
                    "padding": "5px 0px 10px 0px",  # "padding": "top right down left"
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
                    dcc.Graph(id="support:graph_volumes"),
                    dcc.Graph(id="support:graph_taux"),
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
                ]),
                dcc.Graph(id='kpi:graph_kpi'),
            ]),
        ]),
        dcc.Store(id='datastore', data={}),
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
        bucket, path, path.split('/')[-1]
    )
    stats = pd.read_csv(path.split('/')[-1], index_col=0)
    return create_volumes_graph(stats), create_taux_graph(stats)


@app.callback(
    Output("support:download_stats", "data"),
    [Input('support:button_download', 'n_clicks')]
)
def download_data(click):
    if click:
        stats = pd.read_csv(path.split('/')[-1], index_col=0)
        return {
            'content': stats.to_csv(),
            'filename': path.split('/')[-1]
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
        'https://www.data.gouv.fr/fr/datasets/r/79e2c14d-8278-4407-84b5-e8c279fc578c'
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
    kpis = pd.read_json(datastore['kpis'])
    restr = kpis.loc[kpis['indicateur'] == indic].sort_values('date')
    restr['mois'] = restr['date'].apply(lambda d: d.strftime('%Y-%m'))
    restr = restr.drop_duplicates(subset='mois')
    fig = px.bar(
        restr,
        x='mois',
        y='valeur',
        title=indic
    )
    fig.update_layout(
        xaxis_title='Mois',
        yaxis_title=f"Valeur ({restr['unite_mesure'].unique()[0]})",
        yaxis_range=[0, max(restr['valeur'])*1.1]
    )
    return fig


# %%
if __name__ == '__main__':
    app.run_server(debug=False, use_reloader=False, port=8053)
