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
| Building Management | S1 list/create buildings, explicit solar metadata, configured meters | Done |
| Meter Management | S1 add/activate/deactivate meters, required-meter confirmation | Done |
| Costs | S3 cost estimate, tariffs (create/deactivate) | Done |
| Scenarios | S3 what-if scenarios over inclusive UTC dates | Done |
| Alerts | S3 detection, list, resolve | Done |
| Reports | S3 cost reports | Done |
| Forecast | S2 seven-day forecast with bands | Done |
| Recommendations | S2 generate, list and feedback (1-5 rating) | Done |

Demo-mode Docker startup provides 14 complete previous UTC days and a tariff on a
fresh database. New user buildings start empty: configure meters, wait for future
Kafka telemetry and sufficient complete days. The Building Management page remains
accessible even when no buildings exist. Duplicate building names remain selectable
by ID, and all building/meter pages follow API pagination.

Select complete previous UTC dates for scenarios and reports. Meter deactivation
retains history; deactivating main/solar pauses telemetry and requires confirmation.
Backend validation remains authoritative; API error details are displayed.

Interaction tests use mocked HTTP calls:

```sh
python -m unittest discover -s frontend -p 'test_*.py'
```
