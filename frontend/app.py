"""Streamlit dashboard for the Smart Energy Management System.

Run from the repository root with the API running (see docs/docker-development.md):

    pip install -r frontend/requirements.txt
    streamlit run frontend/app.py

S1 provides energy monitoring; S2 provides forecasts, recommendations and
feedback; S3 provides cost, scenario, alert and report views.
"""
import os
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qs

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


def all_rows(path):
    """Follow API pagination without depending on its Docker-internal host name."""
    rows, params = [], {}
    while True:
        data, error = call("GET", path, params=params)
        if error:
            return [], error
        rows.extend(results(data))
        next_url = data.get("next") if isinstance(data, dict) else None
        if not next_url:
            return rows, None
        params = parse_qs(urlsplit(next_url).query)


# --- sidebar ---------------------------------------------------------------
st.sidebar.title("Smart Energy")
buildings, err = all_rows("/buildings/")
show(err)
options = {f"{b['name']} (#{b['id']})": b["id"] for b in buildings}
building_id = options[st.sidebar.selectbox("Building", list(options))] if options else None
page = st.sidebar.radio(
    "Page",
    [
        "Overview",
        "Building Management",
        "Meter Management",
        "Costs",
        "Scenarios",
        "Alerts",
        "Reports",
        "Forecast",
        "Recommendations"
    ]
)
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

def building_management():
    st.header("Building Management (S1)")
    st.caption("New buildings start without readings. Configure meters to enable future synthetic telemetry.")
    if buildings:
        st.dataframe(pd.DataFrame(buildings), width="stretch")
    with st.form("add_building"):
        name = st.text_input("Building name")
        location = st.text_input("Location")
        area = st.number_input("Floor area (m²)", min_value=0.01, value=1000.0)
        baseline = st.number_input("Baseline consumption (kWh/day)", min_value=0.0, value=250.0)
        solar = st.checkbox("Solar installation exists", value=False)
        submitted = st.form_submit_button("Create building")
    if submitted:
        if not name.strip():
            st.error("Please enter a building name.")
        else:
            _, error = call("POST", "/buildings/", json={"name": name.strip(),
                "location": location.strip(), "area_sqm": area,
                "baseline_kwh_per_day": baseline, "has_solar_installation": solar})
            if not show(error):
                st.success("Building created. Select it in the sidebar and add meters.")
                st.rerun()
    if building_id is not None:
        meters, error = all_rows(f"/buildings/{building_id}/meters/")
        if not show(error):
            st.subheader("Selected building's configured meters")
            st.dataframe(pd.DataFrame(meters), width="stretch") if meters else st.info("No meters configured yet.")


def meter_management():
    st.header("Meter Management (S1)")
    st.caption("Manage building meters and their telemetry status.")

    # Get meters for the selected building
    data, err = all_rows(f"/buildings/{building_id}/meters/")

    if show(err):
        return

    meters = results(data)
    selected = next(b for b in buildings if b["id"] == building_id)
    mains = sum(m["is_active"] and m["meter_type"] == "ELECTRICITY" for m in meters)
    solar_count = sum(m["is_active"] and m["meter_type"] == "SOLAR" for m in meters)
    if (mains != 1 or selected["has_solar_installation"] is None
            or (selected["has_solar_installation"] is True and solar_count != 1)
            or (selected["has_solar_installation"] is False and any(m["meter_type"] == "SOLAR" for m in meters))):
        st.warning("Telemetry is paused for an incomplete or conflicting inventory. It needs one active main meter, "
                   "explicit solar status, and one active solar meter if solar is installed.")
    else:
        st.info("Inventory is eligible. New meters participate once their first full minute has completed.")

    st.subheader("Existing Meters")

    if not meters:
        st.info("No meters found for this building.")

    for meter in meters:
        col1, col2 = st.columns([4, 1])

        with col1:
            st.write(f"**{meter['device_id']}**")
            st.caption(
                f"Type: {meter['meter_type_display']} | "
                f"Status: {'Active' if meter['is_active'] else 'Inactive'}"
            )

        with col2:
            active = meter["is_active"]
            button_text = "Deactivate" if active else "Activate"

            required = active and meter["meter_type"] in ("ELECTRICITY", "SOLAR")
            confirmed = not required or st.checkbox("Confirm: pauses building telemetry", key=f"confirm_{meter['id']}")
            if st.button(button_text, key=f"meter_{meter['id']}", disabled=not confirmed):
                updated_status = not active

                _, err = call(
                    "PATCH",
                    f"/meters/{meter['id']}/",
                    json={"is_active": updated_status}
                )

                if not show(err):
                    st.success("Meter status updated!")
                    st.rerun()

    st.divider()

    # Add a new meter
    st.subheader("Add New Meter")

    with st.form("add_meter_form"):
        device_id = st.text_input(
            "Meter Device ID",
            placeholder="METER-HVAC-002"
        )

        meter_type = st.selectbox(
            "Meter Type",
            ["ELECTRICITY", "HVAC", "LIGHTING", "SOLAR"]
        )

        is_active = st.checkbox(
            "Activate immediately",
            value=False
        )

        submitted = st.form_submit_button("Add Meter")

    if submitted:
        if not device_id.strip():
            st.error("Please enter a Meter Device ID.")
        else:
            payload = {
                "device_id": device_id.strip(),
                "meter_type": meter_type,
                "unit": "kWh",
                "is_active": is_active
            }

            _, err = call(
                "POST",
                f"/buildings/{building_id}/meters/",
                json=payload
            )

            if not show(err):
                st.success("New meter added successfully!")
                st.rerun()



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
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = st.date_input("Start date (UTC, inclusive)", yesterday - timedelta(days=13))
    end = st.date_input("End date (UTC, inclusive)", yesterday)
    st.caption(f"Selected period: {start} through {end}, inclusive UTC days. Missing intervals remain unavailable.")
    consumption = st.slider("Consumption change (%)", -100, 100, -10)
    solar = st.slider("Solar output change (%)", -100, 200, 0)
    body = {"consumption_change_pct": consumption, "solar_change_pct": solar,
            "period_start": str(start), "period_end": str(end)}
    if st.checkbox("Use an alternative tariff"):
        body["tariff"] = {
            "rate_standard_eur_per_kwh": st.number_input("Standard EUR/kWh", 0.0, value=0.25, step=0.01),
            "rate_peak_eur_per_kwh": st.number_input("Peak EUR/kWh", 0.0, value=0.40, step=0.01),
        }
    if st.button("Run scenario"):
        if start > end:
            st.error("Start date must not be after end date.")
            return
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
    st.header("Forecast")
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
    st.header("Recommendations")
    st.caption("Recommendations use the configured AI provider or rule-based fallback. "
               "Goals and scores are illustrative; monetary savings belong to S3.")
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


PAGES = {
    "Overview": overview,
    "Building Management": building_management,
    "Meter Management": meter_management,
    "Costs": costs,
    "Scenarios": scenarios,
    "Alerts": alerts,
    "Reports": reports,
    "Forecast": forecast,
    "Recommendations": recommendations
}

if building_id is None and page != "Building Management":
    st.info("No building selected. Open Building Management to create the first building.")
else:
    PAGES[page]()
