import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output

import pandas as pd
from io import StringIO
import plotly.express as px
import plotly.graph_objects as go

from tabs.utils import get_file_content

support_file = "stats_support.csv"

tab_support = dcc.Tab(label="Support", children=[
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
        style={"padding": "15px 0px 5px 0px"},
    ),
])


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


# %% Callbacks
@dash.callback(
    [
        Output('support:graph_volumes', 'figure'),
        Output('support:graph_taux', 'figure'),
    ],
    [Input('support:button_refresh', 'n_clicks')]
)
def update_dropdown_options(click):
    stats = pd.read_csv(
        StringIO(
            get_file_content(support_file)
        ),
        index_col=0
    )
    return create_volumes_graph(stats), create_taux_graph(stats)


@dash.callback(
    Output("support:download_stats", "data"),
    [Input('support:button_download', 'n_clicks')],
    prevent_initial_call=True,
)
def download_data_support(click):
    if click:
        return {
            'content': (
                get_file_content(support_file)
            ),
            'filename': support_file
        }
    return
