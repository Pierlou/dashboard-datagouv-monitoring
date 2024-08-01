from minio import Minio
import requests
from my_secrets import DATAGOUV_API_KEY

bucket = "dataeng-open"
folder = "dashboard/"
max_displayed_suggestions = 10

client = Minio(
    "object.files.data.gouv.fr",
    secure=True,
)


def get_file_content(
    file_path,
    client=client,
    bucket=bucket,
    encoding="utf-8",
):
    r = client.get_object(bucket, folder + file_path)
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


def first_day_same_month(date):
    return date[:7] + '-01'


def get_all_from_api_query(
    base_query,
    next_page='next_page',
    ignore_errors=False,
    mask=None,
):
    def get_link_next_page(elem, separated_keys):
        result = elem
        for k in separated_keys.split('.'):
            result = result[k]
        return result
    # will need this to access reports endpoint
    headers = {"X-API-KEY": DATAGOUV_API_KEY}
    if mask is not None:
        headers["X-fields"] = mask + f",{next_page}"
    while True:
        try:
            r = requests.get(base_query, headers=headers, timeout=5)
            break
        except Exception as e:
            print(e)
    if not ignore_errors:
        r.raise_for_status()
    for elem in r.json()["data"]:
        yield elem
    while get_link_next_page(r.json(), next_page):
        while True:
            try:
                r = requests.get(
                    get_link_next_page(r.json(), next_page),
                    headers=headers,
                    timeout=5
                )
                break
            except Exception as e:
                print(e)
        if not ignore_errors:
            r.raise_for_status()
        for data in r.json()['data']:
            yield data


def add_total_top_bar(fig, df, x, y):
    totals = df.groupby(x)[y].sum().reset_index()
    for _, row in totals.iterrows():
        fig.add_annotation(
            x=row[x],
            y=row[y],
            text=str(row[y]),
            showarrow=False,
            font=dict(size=12, color='black'),
            yshift=10,
        )


DATASETS_QUALITY_METRICS = [
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

DATASERVICES_QUALITY_METRICS = [
    {
        'label': "URL de l'API",
        'value': 'base_api_url'
    },
    {
        'label': 'Point de contact',
        'value': 'contact_point'
    },
    {
        'label': 'Description sur data.gouv',
        'value': 'description'
    },
    {
        'label': 'URL de description',
        'value': 'endpoint_description_url'
    },
    {
        'label': 'Licence',
        'value': 'license'
    }
]
