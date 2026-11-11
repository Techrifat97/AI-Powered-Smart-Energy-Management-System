"""Streamlit dashboard for the Smart Energy Management System.

Run from the repository root with the API running (see docs/docker-development.md):

    pip install -r frontend/requirements.txt
    streamlit run frontend/app.py

S1 (overview) and S3 (costs, scenarios, alerts, reports) are wired up. The S2
pages (forecast, recommendations, feedback) are placeholders to consume later.
"""
import os
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("SMART_ENERGY_API", "http://127.0.0.1:8000/api").rstrip("/")

st.set_page_config(page_title="Smart Energy Dashboard", page_icon=":zap:", layout="wide")


def call(method, path, **kwargs):
    """Return (data, error). Never raises, so the page can show a friendly message."""
    try:
        response = requests.request(method, f"{API}{path}", timeout=15, **kwargs)
    except requests.RequestException as error:
        return None, f"API not reachable at {API}: {error}"
    try:
        data = response.json()
    except ValueError:
        data = None
    if response.status_code >= 400:
        return data, f"HTTP {response.status_code}: {data}"
    return data, None


def show(error):
    if error:
        st.error(error)
        return True
    return False


def results(data):
    return data["results"] if isinstance(data, dict) and "results" in data else (data or [])


def metric(label, value, unit=""):
    st.metric(label, "n/a" if value is None else f"{value:,.2f}{unit}")


# --- sidebar ---------------------------------------------------------------
st.sidebar.title("Smart Energy")
buildings, err = call("GET", "/buildings/")
if show(err) or not results(buildings):
    st.warning("No building found. Run `setup_demo_inventory` (see docs/docker-development.md).")
    st.stop()
options = {b["name"]: b["id"] for b in results(buildings)}
building_id = options[st.sidebar.selectbox("Building", list(options))]
page = st.sidebar.radio("Page", ["Overview", "Costs", "Scenarios", "Alerts", "Reports",
                                 "Forecast (S2)", "Recommendations (S2)"])
if st.sidebar.button("Refresh"):
    st.rerun()
st.sidebar.caption(f"API: {API}")


# --- pages -----------------------------------------------------------------
def overview():
    st.header("Overview")
    summary, err = call("GET", f"/buildings/{building_id}/summary/")
    if show(err):
        return
    cols = st.columns(4)
    with cols[0]:
        metric("Total consumption", summary["total_consumption_kwh"], " kWh")
    with cols[1]:
        metric("Solar generated", summary["total_solar_generated_kwh"], " kWh")
    with cols[2]:
        metric("Peak demand", summary["peak_demand_kw"], " kW")
    with cols[3]:
        metric("Readings", summary["total_readings_count"])
    if not summary["main_data_available"]:
        st.info(f"Main data unavailable: {summary['main_data_reason']}")
    st.caption(f"Latest reading: {summary['latest_reading']} | active meters: {summary['active_meters_count']}")
    readings, err = call("GET", f"/buildings/{building_id}/readings/")
    if show(err):
        return
    rows = results(readings)
    if rows:
        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        st.subheader("Power by meter (latest page of readings)")
        st.line_chart(frame.pivot_table(index="timestamp", columns="meter_type", values="power_kw"))
        st.dataframe(frame[["timestamp", "meter_device_id", "meter_type", "energy_kwh", "power_kw"]],
                     width="stretch")


def costs():
    st.header("Costs")
    tariffs, err = call("GET", "/tariffs/")
    if show(err):
        return
    active = [t for t in results(tariffs) if t["is_active"]]
    if not active:
        st.warning("No active tariff. Create one to enable cost estimates.")
    else:
        st.caption(f"Active tariff: {active[0]['name']}")
    cost, err = call("GET", f"/buildings/{building_id}/cost/")
    if not show(err) and cost:
        if cost["cost_estimates_available"]:
            cols = st.columns(3)
            with cols[0]:
                metric("Import cost", cost["estimated_import_cost_eur"], " EUR")
            with cols[1]:
                metric("Export credit", cost["estimated_export_credit_eur"], " EUR")
            with cols[2]:
                metric("Net cost", cost["estimated_net_cost_eur"], " EUR")
            st.caption(cost["pricing_scope"])
        else:
            st.info(f"Cost estimate unavailable: {cost['cost_estimates_reason']}")
    with st.expander("Create tariff"):
        with st.form("tariff"):
            name = st.text_input("Name", "Demo flat tariff")
            standard = st.number_input("Standard rate EUR/kWh", 0.0, value=0.30, step=0.01)
            peak = st.number_input("Peak rate EUR/kWh", 0.0, value=0.30, step=0.01)
            start = st.number_input("Peak start hour (UTC)", 0, 23, 11)
            end = st.number_input("Peak end hour (UTC)", 0, 23, 16)
            feed_in = st.number_input("Feed-in EUR/kWh", 0.0, value=0.08, step=0.01)
            if st.form_submit_button("Create"):
                _, err = call("POST", "/tariffs/", json={
                    "name": name, "rate_standard_eur_per_kwh": standard, "rate_peak_eur_per_kwh": peak,
                    "peak_start_hour": int(start), "peak_end_hour": int(end),
                    "solar_feed_in_eur_per_kwh": feed_in, "is_active": True})
                if not show(err):
                    st.success("Tariff created.")
                    st.rerun()
    for tariff in active:
        if st.button(f"Deactivate '{tariff['name']}'", key=f"off{tariff['id']}"):
            _, err = call("PATCH", f"/tariffs/{tariff['id']}/", json={"is_active": False})
            if not show(err):
                st.rerun()


def scenarios():
    st.header("What-if scenarios")
    consumption = st.slider("Consumption change (%)", -100, 100, -10)
    solar = st.slider("Solar output change (%)", -100, 200, 0)
    body = {"consumption_change_pct": consumption, "solar_change_pct": solar}
    if st.checkbox("Use an alternative tariff"):
        body["tariff"] = {
            "rate_standard_eur_per_kwh": st.number_input("Standard EUR/kWh", 0.0, value=0.25, step=0.01),
            "rate_peak_eur_per_kwh": st.number_input("Peak EUR/kWh", 0.0, value=0.40, step=0.01),
        }
    if st.button("Run scenario"):
        data, err = call("POST", f"/buildings/{building_id}/scenarios/", json=body)
        if show(err):
            return
        if not data["available"]:
            st.info(f"Scenario unavailable: {data['reason']}")
            return
        base, scen = data["baseline"], data["scenario"]
        cols = st.columns(3)
        with cols[0]:
            metric("Baseline net cost", base["net_cost_eur"], " EUR")
        with cols[1]:
            metric("Scenario net cost", scen["net_cost_eur"], " EUR")
        with cols[2]:
            metric("Difference", data["difference_net_cost_eur"], " EUR")
        st.bar_chart(pd.DataFrame({"net cost EUR": [base["net_cost_eur"], scen["net_cost_eur"]]},
                                  index=["Baseline", "Scenario"]))


def alerts():
    st.header("Alerts")
    if st.button("Run detection"):
        data, err = call("POST", "/alerts/detect/", json={"building_id": building_id})
        if not show(err):
            st.success(f"{data['created_count']} new alert(s).")
    only_open = st.checkbox("Only unresolved", True)
    params = {"building_id": building_id}
    if only_open:
        params["is_resolved"] = "false"
    data, err = call("GET", "/alerts/", params=params)
    if show(err):
        return
    rows = results(data)
    if not rows:
        st.info("No alerts.")
    for alert in rows:
        icon = {"CRITICAL": ":red_circle:", "WARNING": ":orange_circle:"}.get(alert["severity"], ":blue_circle:")
        cols = st.columns([6, 1])
        cols[0].write(f"{icon} **{alert['alert_type_display']}**: {alert['message']} ({alert['created_at']})")
        if not alert["is_resolved"] and cols[1].button("Resolve", key=f"r{alert['id']}"):
            _, err = call("PATCH", f"/alerts/{alert['id']}/", json={"is_resolved": True})
            if not show(err):
                st.rerun()


def reports():
    st.header("Cost reports")
    yesterday = date.today() - timedelta(days=1)
    cols = st.columns(2)
    start = cols[0].date_input("Period start (UTC, inclusive)", yesterday)
    end = cols[1].date_input("Period end (UTC, inclusive)", yesterday)
    if st.button("Generate report"):
        data, err = call("POST", f"/buildings/{building_id}/reports/",
                         json={"period_start": str(start), "period_end": str(end)})
        if err and isinstance(data, dict) and "reason" in data:
            st.info(f"Report unavailable: {data['reason']}")
        elif not show(err):
            st.success("Report stored.")
    data, err = call("GET", f"/buildings/{building_id}/reports/")
    if not show(err) and data:
        st.dataframe(pd.DataFrame(data), width="stretch")
    elif not err:
        st.info("No reports yet. A report needs a tariff and fully covered UTC days.")


def forecast():
    st.header("Forecast (S2)")
    st.caption("Seven-day heuristic forecast. Bands are illustrative, not a calibrated model. "
               "Needs at least two fully covered UTC days in the last 14 days.")
    data, err = call("GET", f"/buildings/{building_id}/forecast/")
    if show(err):
        return
    rows = data.get("forecast") or []
    if not rows:
        reason = (data.get("availability") or {}).get("reason", "unknown")
        st.info(f"Forecast unavailable: {reason}")
    else:
        cols = st.columns(2)
        with cols[0]:
            metric("Predicted next 7 days", data["total_predicted_7d_kwh"], " kWh")
        with cols[1]:
            metric("Average per day", data["avg_daily_predicted_kwh"], " kWh")
        frame = pd.DataFrame(rows)
        frame["forecast_date"] = pd.to_datetime(frame["forecast_date"])
        st.line_chart(frame.set_index("forecast_date")[
            ["predicted_kwh", "confidence_lower_kwh", "confidence_upper_kwh"]])
        st.dataframe(frame[["forecast_date", "predicted_kwh", "confidence_lower_kwh",
                            "confidence_upper_kwh", "trend"]], width="stretch")
    with st.expander("Availability details"):
        st.json(data.get("availability") or {})


def recommendations():
    st.header("Recommendations (S2)")
    st.caption("Rule-based by default (external AI is disabled in Docker). Goals and scores are "
               "illustrative; monetary savings belong to S3.")
    target = st.slider("Target savings (%)", 1, 50, 15)
    if st.button("Generate recommendations"):
        data, err = call("POST", "/recommendations/generate/",
                         json={"building_id": building_id, "target_savings_pct": target})
        if show(err):
            return
        availability = data.get("availability") or {}
        if not availability.get("available"):
            st.info(f"Not enough data yet: {availability.get('reason')}")
        else:
            st.success(f"{len(data.get('recommendations', []))} recommendation(s) stored "
                       f"(engine: {data['engine_telemetry']['source']}).")
        with st.expander("Sustainability assessment"):
            st.json(data.get("sustainability_assessment") or {})
    st.subheader("Stored recommendations")
    data, err = call("GET", "/recommendations/", params={"building_id": building_id})
    if show(err):
        return
    rows = results(data)
    if not rows:
        st.info("No recommendations yet. They need the same complete-day history as forecasts.")
    for rec in rows:
        with st.container(border=True):
            st.markdown(f"**{rec['title']}**  \n{rec['category_display']} | priority "
                        f"{rec['priority_display']} | source {rec['source']} | status {rec['status']}")
            st.write(rec["suggested_action"])
            st.caption(f"Estimated saving: {rec['estimated_savings_kwh']} kWh | "
                       f"confidence: {rec['confidence_score']}")
            with st.form(f"feedback{rec['id']}"):
                rating = st.slider("Rating", 1, 5, 5, key=f"rate{rec['id']}")
                accepted = st.checkbox("Accepted", True, key=f"acc{rec['id']}")
                comment = st.text_input("Comment", key=f"com{rec['id']}")
                if st.form_submit_button("Send feedback"):
                    _, err = call("POST", f"/recommendations/{rec['id']}/feedback/",
                                  json={"rating": rating, "is_accepted": accepted, "comment": comment})
                    if not show(err):
                        st.success("Feedback stored.")


PAGES = {"Overview": overview, "Costs": costs, "Scenarios": scenarios, "Alerts": alerts,
         "Reports": reports, "Forecast (S2)": forecast, "Recommendations (S2)": recommendations}
PAGES[page]()
