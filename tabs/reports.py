import dash
from dash import dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from dash import html

import pandas as pd
import plotly.express as px

from tabs.utils import (
    get_all_from_api_query,
    add_total_top_bar,
)

reasons = {
    "personal_data": "Données personnelles",
    "explicit_content": "Contenu explicite",
    "illegal_content": "Contenu illégal",
    "others": "Autres",
    "security": "Sécurité",
    "spam": "Spam",
}
subjects = {
    'Dataset': 'Jeu de données',
    'Organization': 'Organisation',
    'Reuse': 'Réutilisation',
    'Reuse': 'Réutilisation',
    'Dataservie': 'API',
    'Discussion': 'Discussion',
}

tab_reports = dcc.Tab(label="Signalements", children=[
    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id="reports:dropdown_subject_class",
                placeholder="Choisir un type de données...",
                # can't use None as a default value
                value="all",
                options=[
                    {
                        'label': 'Tous les objets',
                        'value': "all",
                    },
                ] + [{'label': v, 'value': k} for k, v in subjects.items()]
            ),
        ]),
        dbc.Col([
            dcc.Dropdown(
                id="reports:dropdown_reason",
                placeholder="Choisir un motif de signalement...",
                value="all",
                options=[
                    {
                        'label': 'Tous les motifs',
                        'value': "all",
                    },
                ] + [{'label': v, 'value': k} for k, v in reasons.items()]
            ),
        ]),
    ],
        style={"padding": "15px 0px 5px 0px"},
    ),
    html.Div(id='reports:graph'),
])


# %% Callbacks
@dash.callback(
    Output("reports:graph", "children"),
    [
        Input("reports:dropdown_subject_class", 'value'),
        Input("reports:dropdown_reason", 'value'),
    ],
)
def refresh_reports_graph(subject_class, reason):
    # works for now, maybe we'll need something
    # smarter when there are more reports
    reports = get_all_from_api_query("https://www.data.gouv.fr/api/1/reports/")
    data = []
    for r in reports:
        if (
            (subject_class == "all" or r['subject']['class'] == subject_class)
            and (reason == "all" or r['reason'] == reason)
        ):
            data.append({
                "month": r['reported_at'][:8] + "01",
                "reason": r['reason'],
                "subject_class": r['subject']['class'],
                "reported_at": r['reported_at'],
                "subject_deleted_at": r['subject_deleted_at'],
            })
    if not data:
        return html.H5('Aucun signalement ne correspond à ces critères.')
    df = pd.DataFrame(data)[["month", "reason", "subject_class"]]
    df['reason'] = df['reason'].apply(lambda x: reasons[x])
    df['subject_class'] = df['subject_class'].apply(lambda x: subjects[x])
    color = None
    if reason != "all" and subject_class != "all":
        volumes = df['month'].value_counts().reset_index().rename(
            {'index': 'Mois', 'month': 'Volume'},
            axis=1
        )
        title = (
            f'Signalements par mois pour le motif `{reason}`'
            f' et les {subject_class.lower()}s'
        )

    elif reason == "all":
        color = "Motif"
        volumes = df[['month', 'reason']].value_counts().reset_index().rename(
            {'month': 'Mois', 'reason': color, 'count': 'Volume'},
            axis=1
        )
        title = 'Signalements par mois pour tous les motifs et '
        if subject_class == "all":
            title += 'tous les objets'
        else:
            title += f'les {subject_class.lower()}s'

    else:
        color = "Objet"
        volumes = df[['month', 'subject_class']].value_counts().reset_index().rename(
            {'month': 'Mois', 'subject_class': color, 'count': 'Volume'},
            axis=1
        )
        title = f'Signalements par mois pour le motif `{reason}` et tous les objets'

    fig = px.bar(
        volumes,
        x="Mois",
        y="Volume",
        color=color,
        text_auto=True,
        title=title,
    )
    add_total_top_bar(fig=fig, df=volumes, x="Mois", y="Volume")
    fig.update_layout(
        xaxis=dict(
            title='Mois',
            tickformat="%b 20%y",
        ),
    )
    return [dcc.Graph(figure=fig)]
