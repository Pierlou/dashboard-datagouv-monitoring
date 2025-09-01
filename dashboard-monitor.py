# -*- coding: utf-8 -*-

from dash import dcc
from dash import html
import dash_auth
# import dash_daq as daq
import dash_bootstrap_components as dbc
from my_secrets import (
    VALID_USERNAME_PASSWORD_PAIRS,
)
from maindash import app
from tabs.support import tab_support
from tabs.kpi_and_catalog import tab_kpi_catalog
from tabs.reuses import tab_reuses
from tabs.certif import tab_certif
from tabs.hvd import tab_hvd
from tabs.reports import tab_reports
# from tabs.siret import tab_siret

auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)


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
            tab_reuses,
            tab_certif,
            tab_hvd,
            tab_reports,
            # tab_siret,
        ]),
    ]
)

# %%
if __name__ == '__main__':
    app.run_server(debug=False, use_reloader=False, port=8053)
