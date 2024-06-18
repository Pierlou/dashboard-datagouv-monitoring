import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json

from tabs.utils import (
    get_file_content,
    get_latest_day_of_each_month,
)


tab_kpi_catalog = dcc.Tab(label="KPIs & catalogue", children=[
    html.H5('KPIs de data.gouv'),
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
        style={"padding": "15px 0px 5px 0px"},
    ),
    dcc.Graph(id='kpi:graph_kpi'),
    html.H5('Qualité des jeux de données'),
    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id="catalog:dropdown_quality_indicator",
                placeholder="Choisir un critère qualité...",
                options=[
                    {
                        'label': 'Tous les fichiers sont disponibles',
                        'value': 'all_resources_available',
                    },
                    {
                        'label': 'Description des données renseignée',
                        'value': 'dataset_description_quality',
                    },
                    {
                        'label': 'Formats de fichiers standards',
                        'value': 'has_open_format',
                    },
                    {
                        'label': 'Au moins une ressource',
                        'value': 'has_resources',
                    },
                    {
                        'label': 'Licence renseignée',
                        'value': 'license',
                    },
                    {
                        'label': 'Fichiers documentés',
                        'value': 'resources_documentation',
                    },
                    {
                        'label': 'Score qualité global',
                        'value': 'score',
                    },
                    {
                        'label': 'Couverture spatiale renseignée',
                        'value': 'spatial',
                    },
                    {
                        'label': 'Couverture temporelle renseignée',
                        'value': 'temporal_coverage',
                    },
                    {
                        'label': 'Fréquence de mise à jour respectée',
                        'value': 'update_fulfilled_in_time',
                    },
                    {
                        'label': 'Fréquence de mise à jour renseignée',
                        'value': 'update_frequency',
                    },
                ]
            ),
        ]),
        dbc.Col([
            dcc.Dropdown(
                id="catalog:dropdown_datasets_types",
                placeholder="Choisir le scope...",
                options=[
                    {
                        'label': 'Tous les jeux de données',
                        'value': 'all'
                    },
                    {
                        'label': 'Jeux de données moissonnés',
                        'value': 'harvested'
                    },
                    {
                        'label': 'Jeux de données statiques',
                        'value': 'local'
                    },
                ]
            ),
        ]),
    ],
        style={"padding": "15px 0px 5px 0px"},
    ),
    dcc.Graph(id='catalog:datasets_types'),
    html.H5('Types et formats des ressources'),
    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id="catalog:dropdown_resources_types",
                options=[
                    {
                        'label': 'Tous les types de ressources',
                        'value': 'all'
                    },
                    {
                        'label': 'Ressources principales',
                        'value': 'main'
                    },
                    {
                        'label': 'Documentations',
                        'value': 'documentation'
                    },
                    {
                        'label': 'API',
                        'value': 'api'
                    },
                    {
                        'label': 'Mises à jour',
                        'value': 'update'
                    },
                    {
                        'label': 'Code source',
                        'value': 'code'
                    },
                ]
            ),
        ]),
        dbc.Col([
            dbc.Row(children=[
                html.H6('% seuil du groupe "Autres formats"'),
                dcc.Slider(
                    min=0.2,
                    max=3,
                    step=0.2,
                    value=2,
                    id='catalog:slider'
                ),
            ]),
        ]),
    ],
        style={"padding": "15px 0px 5px 0px"},
    ),
    dcc.Graph(id='catalog:resources_types'),
])


# %% Callbacks
@dash.callback(
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


@dash.callback(
    Output("kpi:dropdown", "options"),
    [Input('datastore', 'data')],
)
def refresh_kpis_dropdown(datastore):
    kpis = pd.read_json(datastore['kpis'])
    options = [
        {'label': k, 'value': k} for k in kpis['indicateur'].unique()
    ]
    return options


@dash.callback(
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
        title=indic,
        text_auto=True,
    )
    fig.update_layout(
        xaxis=dict(
            title='Mois',
            tickformat="%b 20%y",
        ),
        yaxis_title=f"Valeur ({restr['unite_mesure'].unique()[0]})",
        yaxis_range=[0, max(restr['valeur'])*1.1]
    )
    return fig


@dash.callback(
    Output("catalog:datasets_types", "figure"),
    [
        Input('catalog:dropdown_datasets_types', 'value'),
        Input('catalog:dropdown_quality_indicator', 'value'),
    ]
)
def change_datasets_quality_graph(indic, param):
    if not indic or not param:
        raise PreventUpdate
    datasets_quality = json.loads(
        get_file_content("datasets_quality.json")
    )
    dates = get_latest_day_of_each_month(datasets_quality.keys())
    data = []
    for date in dates.values():
        data.append([date, datasets_quality[date][indic][param]])
    df = pd.DataFrame(data, columns=('date', 'moyenne'))
    fig = px.bar(df, x="date", y="moyenne", text_auto=True)
    volumes = [[
        d,
        datasets_quality[d]['count'][indic]
    ] for d in datasets_quality]
    fig.add_trace(go.Scatter(
        x=[v[0] for v in volumes],
        y=[v[1] for v in volumes],
        mode='lines',
        name='Nombre de jeux de données',
        yaxis='y2'
    ))
    fig.update_layout(
        xaxis=dict(
            title='Mois',
            tickformat="%b 20%y",
        ),
        yaxis_title="Score moyen pour le critère sélectionné",
        yaxis_range=[0, 1],
        yaxis2=dict(
            title='Nombre de jeux de données',
            overlaying='y',
            side='right',
            range=[0, max([v[1] for v in volumes]) * 1.1]
        ),
        legend=dict(
            orientation='h',
            y=1.1,
            x=0
        )
    )
    return fig


@dash.callback(
    Output("catalog:resources_types", "figure"),
    [
        Input('catalog:dropdown_resources_types', 'value'),
        Input('catalog:slider', 'value'),
    ]
)
def change_resources_types_graph(indic, percent_threshold):
    if not indic:
        raise PreventUpdate
    data = []
    resources_stats = json.loads(
        get_file_content("resources_stats.json")
    )
    dates = get_latest_day_of_each_month(resources_stats.keys())
    for date in dates.values():
        for t in resources_stats[date][indic]:
            data.append([date, t, resources_stats[date][indic][t]])
    df = pd.DataFrame(data, columns=('date', 'format', 'count'))
    threshold = percent_threshold / 100 * df.loc[
        df['date'] == max(df['date']), 'count'
    ].sum()
    final = df.loc[df['count'] > threshold]
    other = df.loc[df['count'] <= threshold]
    for date in other['date'].unique():
        final = pd.concat([
            final,
            pd.DataFrame([[
                date,
                'Autres formats',
                other.loc[other['date'] == date, 'count'].sum()
            ]], columns=final.columns)
        ])
    final.sort_values(by='count', ascending=False, inplace=True)
    y_max = max([
        sum(final.loc[final['date'] == date, 'count'])
        for date in final['date'].unique()
    ])
    fig = px.bar(
        final,
        x="date",
        y="count",
        color="format",
        text_auto=True,
    )
    fig.update_layout(
        xaxis=dict(
            title='Mois',
            tickformat="%b 20%y",
        ),
        yaxis_title="Nombre de ressources par format de fichier",
        yaxis_range=[0, y_max*1.1]
    )
    return fig
