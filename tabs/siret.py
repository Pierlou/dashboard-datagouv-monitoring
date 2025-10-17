import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import pandas as pd
import requests
import re
from unidecode import unidecode
from thefuzz import fuzz
from time import sleep

from my_secrets import (
    DATAGOUV_API_KEY,
)
from tabs.utils import (
    max_displayed_suggestions,
    every_second_row_style,
)

duplicate_slug_pattern = r"-\d+$"
entreprises_api_url = "https://recherche-entreprises.api.gouv.fr/search?q="

tab_siret = dcc.Tab(
    label="SIRETisation (IRVE)",
    children=[
        dbc.Row(
            children=[
                dbc.Col(
                    id="siret:tooltip",
                    children=[
                        html.H3("Correspondances SIRETs trouvés dans les IRVE :"),
                    ],
                    width=9,
                ),
                dbc.Tooltip(
                    "Dans un souci de performances, seules "
                    f"{max_displayed_suggestions} sont affichées. "
                    "Une fois celles-ci traîtées, rafraîchir les données "
                    "pour en afficher plus.",
                    target="siret:tooltip",
                    placement="bottom",
                ),
                dbc.Col(
                    children=[
                        dbc.Row(
                            children=[
                                html.H6("Tolérance du matching"),
                                dcc.Slider(
                                    min=0, max=90, step=10, value=70, id="siret:slider"
                                ),
                            ]
                        ),
                        dbc.Row(
                            children=[
                                dbc.Button(
                                    id="siret:button_refresh",
                                    children=("Rafraîchir les données"),
                                ),
                            ]
                        ),
                    ],
                    width=3,
                ),
            ],
            style={"padding": "15px 0px 5px 0px"},
        ),
        html.Div(id="siret:matches"),
    ],
)


def clean(text):
    if isinstance(text, str):
        if re.search(duplicate_slug_pattern, text) is not None:
            suffix = re.findall(duplicate_slug_pattern, text)[0]
            text = text[: -len(suffix)]
        return unidecode(text.lower()).replace("-", "")
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
    except Exception:
        sleep(1)
        try:
            r = requests.get(entreprises_api_url + siren)
        except Exception:
            return None
    if not r.ok:
        return None
    r = r.json()["results"]
    if len(r) == 0:
        print("No result")
        return None
    if len(r) > 1:
        print("Ambiguous :", len(r))
        return None
    else:
        return r[0]["siege"]["siret"]


# %% Callbacks
@dash.callback(
    Output("siret:matches", "children"),
    [Input("siret:button_refresh", "n_clicks")],
    [State("siret:slider", "value")],
)
def refresh_siret(click, slider):
    df = pd.read_csv(
        "https://www.data.gouv.fr/fr/datasets/r/eb76d20a-8501-400e-b336-d85724de5435",
        dtype=str,
        usecols=[
            "nom_amenageur",
            "siren_amenageur",
            "datagouv_organization_or_owner",
        ],
    )
    restr = df.loc[
        (~df["siren_amenageur"].isna()) & (~df["nom_amenageur"].isna())
    ].drop_duplicates()
    restr["cleaned_nom"] = restr["nom_amenageur"].apply(clean)
    restr["cleaned_orga"] = restr["datagouv_organization_or_owner"].apply(clean)
    restr["ratio"] = restr.apply(
        lambda df_: symetric_ratio(df_["cleaned_orga"], df_["cleaned_nom"]), axis=1
    )
    restr = restr.loc[restr["ratio"] > slider]
    siret_divs = []
    session = requests.Session()
    for orga in restr["datagouv_organization_or_owner"].unique():
        if len(siret_divs) == max_displayed_suggestions:
            break
        tmp = restr.loc[
            restr["datagouv_organization_or_owner"] == orga
        ].drop_duplicates("siren_amenageur")
        if len(tmp) == 1:
            siren = list(tmp["siren_amenageur"])[0]
            siret = get_siret_from_siren(siren)
            if not siret:
                continue
            slug = list(tmp["datagouv_organization_or_owner"])[0]
            r = session.get(
                f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
                headers={"X-fields": "name,business_number_id"},
            ).json()
            if r["business_number_id"]:
                # print(orga, 'already has siret:', r['business_number_id'])
                continue
            match = list(tmp["nom_amenageur"])[0]
            md1 = (
                f"[{r['name']}](https://www.data.gouv.fr/fr/{slug}/) "
                f"matchée avec {match}"
            )
            md2 = f"\nSIREN : {siren}, SIRET : {siret}"
            siret_divs += [
                dbc.Row(
                    children=[
                        dbc.Col(children=[dcc.Markdown(md1), dcc.Markdown(md2)]),
                        dbc.Col(
                            children=[
                                html.Div(
                                    dbc.Button(
                                        id={
                                            "type": "siret",
                                            "index": f"siret:button_{len(siret_divs)}_{slug}_{siret}",
                                        },
                                        children="SIRETiser cette organisation",
                                        color="info",
                                    ),
                                    style={"padding": "10px 0px 0px 0px"},
                                )
                            ]
                        ),
                    ],
                    style=every_second_row_style(len(siret_divs)),
                )
            ]
    return siret_divs


@dash.callback(
    Output("siret:matches", "children", allow_duplicate=True),
    [Input({"type": "siret", "index": dash.ALL}, "n_clicks")],
    prevent_initial_call=True,
)
def update_after_siret(*args):
    patched_children = dash.Patch()
    if all([a is None for a in args[0]]):
        raise PreventUpdate
    # par construction, don't worry it works
    idx, slug, siret = eval(dash.ctx.triggered[0]["prop_id"].split(".")[0])[
        "index"
    ].split("_")[-3:]
    idx = int(idx)
    # r = requests.get(
    #     f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
    #     headers={'X-fields': 'name'},
    # )
    r = requests.put(
        f"https://www.data.gouv.fr/api/1/organizations/{slug}/",
        json={"business_number_id": siret},
        headers={"X-API-KEY": DATAGOUV_API_KEY},
    )
    if not r.ok:
        patched_children[idx] = dbc.Row(
            children=[
                html.H4(
                    "Une erreur est survenue "
                    "en essayant de SIRETiser [cette organisation]"
                    f"(https://www.data.gouv.fr/fr/organizations/{slug}/)"
                )
            ],
            style={"background-color": "#ffb6c1"},
        )
        return patched_children

    r = r.json()
    patched_children[idx] = dbc.Row(
        children=[
            dcc.Markdown(
                children=[
                    f"[{r['name']}]"
                    f"(https://www.data.gouv.fr/fr/organizations/{slug}/)"
                    f" : siretisée avec {siret}"
                ]
            )
        ],
        style={"background-color": "#90ee90"},
    )
    return patched_children
