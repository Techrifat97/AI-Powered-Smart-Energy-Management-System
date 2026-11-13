# Streamlit dashboard

Compose runs this frontend on port 8501. It calls the Django API with JWT bearer
tokens and provides Overview, Building Management, Meter Management, Team Management,
Costs, Scenarios, Alerts, Reports, Forecast and Recommendations pages.

Setup, demo login, usage and test commands are maintained in the root README.
The technical guides document the subsystem APIs and data flow.
[Project setup and usage](../README.md)

For optional host execution, activate a virtual environment with the frontend
dependencies installed and run `streamlit run frontend/app.py`. The default API
address is `http://127.0.0.1:8000/api`. `SMART_ENERGY_API` selects another address.
