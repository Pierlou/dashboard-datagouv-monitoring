# data.gouv.fr dashboard monitor

Dashboard used internally at data.gouv.fr to monitor specific metrics such as [our KPIs](https://www.data.gouv.fr/fr/datasets/indicateurs-dimpact-de-data-gouv-fr/), organizations certifications, resources types and volumes...

## Run

You need to have python >= 3.7 installed. We recommend using a virtual environement.

```
pip install -r requirements.txt
```

You may want to fill in a `my_secrets.py` file (from the template) with relevant credentials.

And then:

```
python dashboard-monitor.py
```

## Contribute

On a separate branch/fork, you may rework preexisting tabs or add new ones in the `tabs` folder. Please as long as possible use `utils` functions to make maintainance easier.