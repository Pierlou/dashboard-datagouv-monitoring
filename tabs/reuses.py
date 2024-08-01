import dash
from dash import dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO

from tabs.utils import (
    get_file_content,
    get_latest_day_of_each_month,
    add_total_top_bar,
)


tab_reuses = dcc.Tab(label="Reuses", children=[
    dbc.Row([
        dbc.Button(
            id='reuses:button_refresh',
            children='Rafraîchir les données'
        ),
        dcc.Graph(id='reuses:graph'),
    ],
        style={"padding": "15px 0px 5px 0px"},
    ),
])


# %% Callbacks
@dash.callback(
    Output("reuses:graph", "figure"),
    [Input('reuses:button_refresh', 'n_clicks')],
)
def refresh_reuses_graph(click):
    hist = pd.read_csv(StringIO(
        get_file_content('stats_reuses_down.csv')
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
    volumes = pd.melt(
        hist,
        id_vars=['Date'],
        var_name='Type erreur',
        value_name='Nombre'
    )
    fig = px.bar(
        volumes,
        x='Date',
        y='Nombre',
        color='Type erreur',
        title='Nombre de reuses qui renvoient une erreur',
        text_auto=True,
    )
    add_total_top_bar(fig=fig, df=volumes, x="Date", y="Nombre")
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
