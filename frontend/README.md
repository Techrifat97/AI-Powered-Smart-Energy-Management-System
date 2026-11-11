# Streamlit dashboard

A small dashboard over the JSON APIs. It is not started by Docker Compose; it runs
on the host and talks to the API at `http://127.0.0.1:8000/api`.

```sh
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Set `SMART_ENERGY_API` to use another API address.

| Page | Source | Status |
| --- | --- | --- |
| Overview | S1 summary and readings | Done |
| Costs | S3 cost estimate, tariffs (create/deactivate) | Done |
| Scenarios | S3 what-if scenarios | Done |
| Alerts | S3 detection, list, resolve | Done |
| Reports | S3 cost reports | Done |
| Forecast | S2 seven-day forecast with bands | Done |
| Recommendations | S2 generate, list and feedback (1-5 rating) | Done |

Empty states are expected on a fresh database: costs need an active tariff, reports
need fully covered UTC days and forecasts need two complete UTC days.
