import dash
from dash import dcc
from dash import html
from dash import dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

from io import StringIO
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import requests
from unidecode import unidecode
# from random import shuffle

from tabs.utils import (
    DATASETS_QUALITY_METRICS,
    DATASERVICES_QUALITY_METRICS,
    max_displayed_suggestions,
    get_file_content,
    get_latest_day_of_each_month,
    first_day_same_month,
    get_all_from_api_query,
    client,
)


def slugify(s: str) -> str:
    return unidecode(s.lower().replace(" ", "-").replace("'", "-"))


ouverture_hvd_api = (
    "https://grist.numerique.gouv.fr/api/docs/eJxok2H2va3E/tables/Hvd/records"
)
r = requests.get(ouverture_hvd_api).json()
categories = {
    slugify(cat): cat for cat in set(k["fields"]["Thematique"] for k in r["records"])
}
df_ouverture = pd.DataFrame([k["fields"] for k in r["records"]])
dfs = []
for _type in ["Telechargement", "API"]:
    tmp = df_ouverture[
        ["Titre", "Ensemble_de_donnees", "Thematique"]
        + [c for c in df_ouverture.columns if c.endswith(_type)]
    ]
    tmp["type"] = "dataservices" if _type == "API" else "datasets"
    tmp.rename(
        {
            c: c.replace(f"_{_type}", "")
            for c in df_ouverture.columns
            if c.endswith(_type)
        },
        axis=1,
        inplace=True,
    )
    dfs.append(tmp)
df_ouverture = pd.concat(dfs)[["URL", "Ensemble_de_donnees", "Thematique"]]


def create_quality_score_graph():
    score_history = [
        name
        for obj in client.list_objects(
            "data-pipeline-open", prefix="hvd/", recursive=False
        )
        if (name := obj.object_name).endswith("grist_hvd.csv")
    ]
    stats = {
        "date": [],
        "mean": [],
        "count": [],
    }
    for file in score_history:
        df = pd.read_csv(
            StringIO(
                get_file_content(
                    file,
                    bucket="data-pipeline-open",
                    folder="",
                )
            ),
            sep=";",
            dtype=float,
            usecols=["score_qualite_hvd"],
        )
        stats["date"].append(file.split("/")[-1][:7] + "-01")
        stats["mean"].append(round(df["score_qualite_hvd"].mean(), 2))
        stats["count"].append(len(df))
        del df
    df = pd.DataFrame(stats)
    fig = px.bar(df, x="date", y="mean", text_auto=True)
    fig.add_trace(
        go.Scatter(
            x=[d for d in df["date"].values],
            y=[c for c in df["count"].values],
            mode="lines",
            name="Nombre de JdD HVD",
            yaxis="y2",
        )
    )
    fig.update_layout(
        xaxis=dict(
            title="Mois",
            tickformat="%b 20%y",
        ),
        yaxis_title="Score qualité HVD par mois",
        yaxis_range=[0, 1],
        yaxis2=dict(
            title="Nombre de JdD HVD",
            overlaying="y",
            side="right",
            range=[0, max([c for c in df["count"].values]) * 1.1],
        ),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    return fig


tab_hvd = dcc.Tab(
    label="HVD",
    children=[
        html.H5("Qualité des HVD"),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dcc.Dropdown(
                            id="hvd:dropdown_object_type",
                            placeholder="Choisir un type de données...",
                            value="datasets",
                            options=[
                                {
                                    "label": "Jeux de données",
                                    "value": "datasets",
                                },
                                {
                                    "label": "APIs",
                                    "value": "dataservices",
                                },
                            ],
                        ),
                    ]
                ),
                dbc.Col(
                    [
                        dcc.Dropdown(
                            id="hvd:dropdown_quality_indicator",
                            placeholder="Choisir un critère qualité...",
                        ),
                    ]
                ),
            ],
            style={"padding": "15px 0px 5px 0px"},
        ),
        dcc.Graph(id="hvd:datasets_types"),
        dcc.Graph(id="hvd:quality_scores"),
        dbc.Row(id="hvd:objects_to_improve"),
        html.H5("Types et formats des ressources HVD"),
        dbc.Row(
            [
                dbc.Row(
                    children=[
                        html.H6('% seuil du groupe "Autres formats"'),
                        dcc.Slider(min=0.2, max=3, step=0.2, value=2, id="hvd:slider"),
                    ]
                ),
            ],
            style={"padding": "15px 0px 5px 0px"},
        ),
        dcc.Graph(id="hvd:resources_types"),
        dcc.Store(id="hvd:datastore", data={}),
    ],
)


# %% Callbacks
@dash.callback(
    [
        Output("hvd:quality_scores", "figure"),
    ],
    # this is only to make the graph load with the page
    [Input("hvd:slider", "value")],
)
def update_quality_graph(_):
    return create_quality_score_graph()


@dash.callback(
    [
        Output("hvd:dropdown_quality_indicator", "options"),
        Output("hvd:dropdown_quality_indicator", "value"),
    ],
    [
        Input("hvd:dropdown_object_type", "value"),
    ],
)
def update_quality_dropdown_options(value):
    if value == "datasets":
        return DATASETS_QUALITY_METRICS, DATASETS_QUALITY_METRICS[0]["value"]
    elif value == "dataservices":
        return DATASERVICES_QUALITY_METRICS, DATASERVICES_QUALITY_METRICS[0]["value"]


@dash.callback(
    [
        Output("hvd:datasets_types", "figure"),
        Output("hvd:datastore", "data"),
    ],
    [
        Input("hvd:dropdown_quality_indicator", "value"),
        Input("hvd:dropdown_object_type", "value"),
    ],
)
def change_datasets_quality_graph(param, object_type):
    if not param or not object_type:
        raise PreventUpdate

    if object_type == "datasets":
        datasets_quality = json.loads(get_file_content("datasets_quality.json"))
        dates = get_latest_day_of_each_month(datasets_quality.keys())
        data = []
        for date in dates.values():
            if datasets_quality[date].get("hvd"):
                data.append([date, datasets_quality[date]["hvd"][param]])
        df = pd.DataFrame(data, columns=("date", "moyenne"))
        volumes = [
            [first_day_same_month(d), datasets_quality[d]["count"]["hvd"]]
            for d in df["date"].unique()
        ]
        df["date"] = df["date"].apply(first_day_same_month)
        object_text = "de jeux de données"

    elif object_type == "dataservices":
        dataservices_quality = json.loads(
            get_file_content("hvd_dataservices_quality.json")
        )
        dates = get_latest_day_of_each_month(dataservices_quality.keys())
        data = []
        for date in dates.values():
            if dataservices_quality[date]["metrics"].get(param):
                data.append(
                    [
                        date,
                        (
                            dataservices_quality[date]["metrics"][param]
                            / dataservices_quality[date]["count"]
                        ),
                    ]
                )
        df = pd.DataFrame(data, columns=("date", "moyenne"))
        volumes = [
            [first_day_same_month(d), dataservices_quality[d]["count"]]
            for d in df["date"].unique()
        ]
        df["date"] = df["date"].apply(first_day_same_month)
        object_text = "d'APIs"

    fig = px.bar(df, x="date", y="moyenne", text_auto=True)
    fig.add_trace(
        go.Scatter(
            x=[v[0] for v in volumes],
            y=[v[1] for v in volumes],
            mode="lines",
            name=f"Nombre {object_text}",
            yaxis="y2",
        )
    )
    fig.update_layout(
        xaxis=dict(
            title="Mois",
            tickformat="%b 20%y",
        ),
        yaxis_title="Score moyen pour le critère sélectionné",
        yaxis_range=[0, 1],
        yaxis2=dict(
            title=f"Nombre {object_text}",
            overlaying="y",
            side="right",
            range=[0, max([v[1] for v in volumes]) * 1.1],
        ),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    return fig, {"progression": df.iloc[-1]["moyenne"]}


@dash.callback(
    Output("hvd:objects_to_improve", "children"),
    [
        Input("hvd:dropdown_quality_indicator", "value"),
        Input("hvd:dropdown_object_type", "value"),
        Input("hvd:datastore", "data"),
    ],
)
def display_objects_to_improve(param, object_type, store):
    if not param or not object_type:
        raise PreventUpdate
    if store.get("progression") == 1:
        return None
    if param == "score":
        return None
    r = get_all_from_api_query(
        f"https://www.data.gouv.fr/api/1/{object_type}/?tag=hvd",
        mask=(
            "data{title,organization,tags,id,quality,slug}"
            if object_type == "datasets"
            else None
        ),
    )
    # so that we don't always show the same ones
    # but that's slow (turning generator to list)
    # shuffle(r)
    missing = []
    for k in r:
        if len(missing) == max_displayed_suggestions:
            break
        _obj = k
        if object_type == "datasets":
            _obj = k["quality"]
        if (param in _obj and not _obj[param]) or (param not in _obj):
            url = f"https://www.data.gouv.fr/fr/{object_type}/{k['slug']}/"
            missing.append(
                {
                    "URL": url,
                    "Titre": k["title"],
                    "Organisation": k["organization"]["name"],
                    "tag HVD": ", ".join(
                        [categories[t] for t in k["tags"] if t in categories]
                    ),
                    "URL data.gouv": f"[{url}]({url})",
                }
            )
    if not missing:
        return [html.H6("Un problème est survenu lors de la récupération des données")]
    missing = pd.DataFrame(missing)
    merged = pd.merge(
        missing,
        df_ouverture,
        on="URL",
        how="left",
    ).drop("URL", axis=1)
    columns = [
        {"name": ["data.gouv", "Titre"], "id": "titre"},
        {"name": ["data.gouv", "Organisation"], "id": "orga"},
        {"name": ["data.gouv", "tag HVD"], "id": "tag"},
        {"name": ["data.gouv", "URL data.gouv"], "id": "url"},
        {"name": ["ouverture", "Ensemble_de_donnees"], "id": "ensemble"},
        {"name": ["ouverture", "Thematique"], "id": "thematique"},
    ]
    for c in columns:
        c.update({"type": "text", "presentation": "markdown"})
    merged.rename({c["name"][1]: c["id"] for c in columns}, axis=1, inplace=True)
    return [
        html.H6(f"A améliorer (max {max_displayed_suggestions}):"),
        dash_table.DataTable(
            merged.to_dict("records"),
            columns,
            # style_cell={'textAlign': 'left'},
            style_header={
                "backgroundColor": "rgb(210, 210, 210)",
                "color": "black",
                "fontWeight": "bold",
                "textAlign": "center",
            },
            style_data={
                "whiteSpace": "normal",
                "height": "auto",
                "textAlign": "left",
            },
            merge_duplicate_headers=True,
        ),
    ]


@dash.callback(
    Output("hvd:resources_types", "figure"),
    [
        Input("hvd:slider", "value"),
    ],
)
def change_resources_types_graph(percent_threshold):
    data = []
    resources_stats = json.loads(get_file_content("resources_stats.json"))
    dates = get_latest_day_of_each_month(resources_stats.keys())
    for date in dates.values():
        if resources_stats[date].get("hvd"):
            for t in resources_stats[date]["hvd"]:
                data.append([date, t, resources_stats[date]["hvd"][t]])
    df = pd.DataFrame(data, columns=("date", "format", "count"))
    df["date"] = df["date"].apply(first_day_same_month)
    threshold = (
        percent_threshold / 100 * df.loc[df["date"] == max(df["date"]), "count"].sum()
    )
    final = df.loc[df["count"] > threshold]
    other = df.loc[df["count"] <= threshold]
    for date in other["date"].unique():
        final = pd.concat(
            [
                final,
                pd.DataFrame(
                    [
                        [
                            date,
                            "Autres formats",
                            other.loc[other["date"] == date, "count"].sum(),
                        ]
                    ],
                    columns=final.columns,
                ),
            ]
        )
    final.sort_values(by="count", ascending=False, inplace=True)
    y_max = max(
        [
            sum(final.loc[final["date"] == date, "count"])
            for date in final["date"].unique()
        ]
    )
    fig = px.bar(
        final,
        x="date",
        y="count",
        color="format",
        text_auto=True,
    )
    fig.update_layout(
        xaxis=dict(
            title="Mois",
            tickformat="%b 20%y",
        ),
        yaxis_title="Nombre de ressources par format de fichier",
        yaxis_range=[0, y_max * 1.1],
    )
    return fig
