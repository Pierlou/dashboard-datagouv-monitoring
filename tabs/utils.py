from minio import Minio

bucket = "dataeng-open"
folder = "dashboard/"

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
