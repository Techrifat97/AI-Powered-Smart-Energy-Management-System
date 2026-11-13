"""Streamlit dashboard for the Smart Energy Management System.

Run from the repository root with the API running (see docs/docker-development.md):

    pip install -r frontend/requirements.txt
    streamlit run frontend/app.py

S1 provides energy monitoring; S2 provides forecasts, recommendations and
feedback; S3 provides cost, scenario, alert and report views.
"""
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import pandas as pd
import requests
import streamlit as st

ASSETS = Path(__file__).with_name("assets")
API = os.environ.get("SMART_ENERGY_API", "http://127.0.0.1:8000/api").rstrip("/")

st.set_page_config(page_title="Smart Energy Dashboard", page_icon=":zap:", layout="wide")

# Persistent session cache across browser reloads
@st.cache_resource
def get_session_cache():
    return {}


_SESSION_CACHE = get_session_cache()


def call(method, path, **kwargs):
    """Return (data, error). Automatically attaches JWT Bearer token if session exists."""
    headers = kwargs.pop("headers", {}) or {}
    token = st.session_state.get("auth_token")
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(method, f"{API}{path}", timeout=15, headers=headers, **kwargs)
    except requests.RequestException as error:
        return None, f"API not reachable at {API}: {error}"
    try:
        data = response.json()
    except ValueError:
        data = None
    if response.status_code == 401 and not path.startswith("/auth/"):
        _SESSION_CACHE.clear()
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()
    if response.status_code >= 400:
        return data, f"HTTP {response.status_code}: {data}"
    return data, None


# Attempt session restore on browser refresh / reload
if "auth_token" not in st.session_state:
    sid = st.query_params.get("sid")
    cached = None
    if isinstance(sid, str) and sid in _SESSION_CACHE:
        cached = _SESSION_CACHE[sid]
    elif "active_session" in _SESSION_CACHE:
        cached = _SESSION_CACHE["active_session"]

    if cached and isinstance(cached, dict) and "token" in cached:
        st.session_state["auth_token"] = cached["token"]
        st.session_state["auth_user"] = cached.get("user", {})
        st.session_state["session_id"] = cached.get("sid", sid)
        if cached.get("sid"):
            st.query_params["sid"] = cached["sid"]
    else:
        cookies = getattr(st.context, "cookies", None)
        cookie_token = cookies.get("auth_token") if hasattr(cookies, "get") else None
        if isinstance(cookie_token, str) and cookie_token.strip():
            profile, err = call("GET", "/accounts/me/", headers={"Authorization": f"Bearer {cookie_token}"})
            if not err and profile:
                st.session_state["auth_token"] = cookie_token
                st.session_state["auth_user"] = profile

if "auth_token" in st.session_state:
    sid = st.session_state.get("session_id")
    if not sid:
        uname = st.session_state.get("auth_user", {}).get("username", "admin")
        sid = f"s_{uname}_{int(datetime.now(timezone.utc).timestamp())}"
        st.session_state["session_id"] = sid
    session_data = {
        "token": st.session_state["auth_token"],
        "user": st.session_state.get("auth_user", {}),
        "sid": sid,
    }
    _SESSION_CACHE[sid] = session_data
    _SESSION_CACHE["active_session"] = session_data
    if st.query_params.get("sid") != sid:
        st.query_params["sid"] = sid


def show(error):
    if error:
        st.error(error)
        return True
    return False


def results(data):
    return data["results"] if isinstance(data, dict) and "results" in data else (data or [])


def metric(label, value, unit="", help=None):
    st.metric(label, "n/a" if value is None else f"{value:,.2f}{unit}", help=help)


GLOSSARY = {
    "kWh (kilowatt-hour)": "The unit electricity is sold in. A 1,000 W heater running for one hour uses 1 kWh.",
    "kW (kilowatt)": "How much power is being used right now. Think of it as the speed, while kWh is the distance.",
    "Meter": "A device that measures electricity. A building usually has a main meter and, with solar panels, a solar meter.",
    "Tariff": "The price list of your electricity supplier: what one kWh costs, and whether it costs more at busy times.",
    "Peak hours": "The hours of the day when electricity is more expensive.",
    "Feed-in credit": "Money you get for solar power you do not use yourself and send back to the grid.",
    "Baseline": "How much electricity a building normally uses per day. Used to spot unusually high days.",
    "UTC": "The world time standard. All times in this app are UTC, which is 1 hour behind Germany in winter.",
}


def reason_text(reason):
    """Plain-language version of an API reason code."""
    return REASONS.get(reason, "There is not enough data yet. Let the building collect readings for a while.")


def page_intro(what, steps=None):
    """Short plain-language introduction shown at the top of a page."""
    st.write(what)
    if steps:
        with st.expander("How to use this page", icon=":material/help:"):
            for number, step in enumerate(steps, 1):
                st.markdown(f"{number}. {step}")


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


def login_screen():
    col1, col2 = st.columns([1.3, 1], gap="large", vertical_alignment="center")
    with col1:
        st.title(":zap: Smart Energy")
        st.subheader("Spend less on electricity. Waste less energy.")
        st.write("Smart Energy watches the electricity use of your building, shows what it costs, warns you "
                 "when something looks wrong and suggests ways to save.")
        st.image(str(ASSETS / "hero.svg"),
                 alt="Illustration of a campus building with solar panels and a chart showing lower electricity costs")
        points = st.columns(3)
        points[0].markdown(":material/monitoring: **See** how much power you use")
        points[1].markdown(":material/savings: **Save** money with what-if ideas")
        points[2].markdown(":material/lightbulb: **Get tips** from an AI assistant")
    with col2:
        st.subheader("Log in")
        st.caption("Use the account you were given by your team admin.")
        with st.form("login_form"):
            username = st.text_input("Username", value="admin")
            password = st.text_input("Password", type="password", value="admin123")
            submit = st.form_submit_button("Log In", width="stretch", type="primary")
            if submit:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    data, err = call("POST", "/auth/token/", json={"username": username, "password": password})
                    if err:
                        st.error("Authentication failed: Invalid credentials.")
                    elif data and "access" in data:
                        token = data["access"]
                        st.session_state["auth_token"] = token
                        profile, _ = call("GET", "/accounts/me/")
                        user_info = profile or {"username": username}
                        st.session_state["auth_user"] = user_info
                        sid = f"s_{username}_{int(datetime.now(timezone.utc).timestamp())}"
                        st.session_state["session_id"] = sid
                        _SESSION_CACHE[sid] = {"token": token, "user": user_info}
                        _SESSION_CACHE["active_session"] = {"token": token, "user": user_info, "sid": sid}
                        st.query_params["sid"] = sid
                        st.success("Authenticated successfully!")
                        st.rerun()
        st.caption("Default evaluator credentials: `admin` / `admin123`")


building_id = None


@st.cache_data(ttl=300, show_spinner="Loading daily totals...")
def daily_energy(building, token, days=14):
    """Daily kWh used and made by solar for the last `days` days, from the main and solar meters."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    params, rows = {"start": start.isoformat(), "page_size": 500}, []
    for _ in range(100):  # safety limit on pages
        try:
            response = requests.request("GET", f"{API}/buildings/{building}/readings/", params=params,
                                        headers=headers, timeout=15)
            data = response.json()
        except (requests.RequestException, ValueError):
            return None
        if response.status_code >= 400 or not isinstance(data, dict):
            return None
        rows.extend(data.get("results", []))
        if not data.get("next"):
            break
        params = {k: v[-1] for k, v in parse_qs(urlsplit(data["next"]).query).items()}
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    frame = frame[frame["meter_type"].isin(["ELECTRICITY", "SOLAR"])]
    if frame.empty:
        return None
    frame["day"] = pd.to_datetime(frame["timestamp"]).dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    daily = frame.pivot_table(index="day", columns="meter_type", values="energy_kwh", aggfunc="sum").fillna(0)
    daily = daily.rename(columns={"ELECTRICITY": "Electricity used", "SOLAR": "Solar made"})
    daily.columns.name = None
    daily.index.name = "Day"
    return daily


# --- pages -----------------------------------------------------------------
def overview():
    hero_left, hero_right = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with hero_left:
        st.title("Spend less on electricity. Waste less energy.")
        st.write("Smart Energy is your building's energy assistant. It **measures** the electricity your "
                 "building uses, **shows what it costs**, **warns you** when something looks wrong and "
                 "**suggests ways to save**.")
        st.caption("New here? Follow the three steps below, or open \"What can I do here?\" in the sidebar.")
    with hero_right:
        st.image(str(ASSETS / "hero.svg"),
                 alt="Illustration of a campus building with solar panels and a chart showing lower electricity costs")

    steps = st.columns(3)
    journey = [
        ("1. See what is happening", ":material/monitoring:",
         "How much electricity is used right now, and what looks unusual.", "alerts_page", "Open alerts"),
        ("2. Understand the cost", ":material/payments:",
         "What the energy costs, and what you could save with a change.", "costs_page", "Open costs"),
        ("3. Plan and save", ":material/lightbulb:",
         "A 7-day forecast and tips to use less electricity.", "recommendations_page", "Get tips"),
    ]
    for column, (title, icon, text, page_name, label) in zip(steps, journey):
        with column.container(border=True, height="stretch"):
            st.markdown(f"#### {icon} {title}")
            st.write(text)
            target = globals().get(page_name)
            if target is not None:
                st.page_link(target, label=label, icon=":material/arrow_forward:")

    selected = next((b for b in buildings if b["id"] == building_id), None)
    st.subheader(f"Right now: {selected['name']}" if selected else "Right now")
    if selected and selected.get("location"):
        st.caption(f":material/location_on: {selected['location']}")
    summary, err = call("GET", f"/buildings/{building_id}/summary/")
    if show(err):
        return
    open_alerts_data, _ = call("GET", "/alerts/", params={"building_id": building_id, "is_resolved": "false"})
    open_alerts = len(results(open_alerts_data))
    cost_data, _ = call("GET", f"/buildings/{building_id}/cost/")
    net_cost = cost_data.get("estimated_net_cost_eur") if isinstance(cost_data, dict) else None
    if open_alerts:
        st.warning(f"{open_alerts} thing(s) need your attention. Open **Alerts** to see what and how to fix it.",
                   title="Something needs attention", icon=":material/warning:")
    else:
        st.success("No open problems. Your building looks normal.", title="All good", icon=":material/check_circle:")
    with st.container(border=True):
        cols = st.columns(4)
        with cols[0]:
            metric("Electricity used", summary["total_consumption_kwh"], " kWh",
                   help="Total electricity the building used since readings began.")
        with cols[1]:
            metric("Solar power made", summary["total_solar_generated_kwh"], " kWh",
                   help="Electricity produced by the building's own solar panels.")
        with cols[2]:
            st.metric("Open alerts", open_alerts, help="Problems that have not been marked as resolved yet.")
        with cols[3]:
            metric("Estimated cost", net_cost, " EUR",
                   help="What the recorded electricity would cost with your active tariff, after solar credit.")
        st.caption(f"Highest power draw: {summary['peak_demand_kw'] if summary['peak_demand_kw'] is not None else 'n/a'} kW"
                   f" | measurements: {summary['total_readings_count']}")
    if not summary["main_data_available"]:
        st.info(reason_text(summary["main_data_reason"]), title="No usable energy data yet", icon=":material/info:")
    st.caption(f"Last measurement: {summary['latest_reading'] or 'none yet'} | "
               f"working meters: {summary['active_meters_count']}")
    st.subheader("Electricity per day")
    st.caption("Green bars: electricity the building used. Yellow bars: electricity its solar panels made. "
               "The last bar is today, so it is not finished yet.")
    daily = daily_energy(building_id, st.session_state.get("auth_token"))
    if daily is not None and not daily.empty:
        palette = {"Electricity used": "#0B8F6B", "Solar made": "#F5A800"}
        st.bar_chart(daily, stack=False, color=[palette[c] for c in daily.columns], height=320,
                     x_label="Day", y_label="kWh per day")
    else:
        st.info("The chart appears once the meters have sent their first measurements. This can take a few "
                "minutes after the app starts.", icon=":material/hourglass_top:")

    with st.expander("Live view: power over the last minutes", icon=":material/monitoring:"):
        readings, err = call("GET", f"/buildings/{building_id}/readings/")
        rows = results(readings) if not err else []
        if rows:
            frame = pd.DataFrame(rows)
            frame = frame[frame["meter_type"].isin(["ELECTRICITY", "SOLAR"])]
            frame["timestamp"] = pd.to_datetime(frame["timestamp"])
            live = frame.pivot_table(index="timestamp", columns="meter_type", values="power_kw")
            live = live.rename(columns={"ELECTRICITY": "Power used (kW)", "SOLAR": "Solar power (kW)"})
            st.line_chart(live, height=260, x_label="Time (UTC)", y_label="kW")
            st.caption("kW is how much power is used at that moment. It goes up and down during the day.")
        else:
            st.caption("No live measurements yet.")


def building_management():
    st.header("Building management")
    page_intro("A building is the place whose energy you want to follow, such as an office, a school or a house. "
               "Add it here, then add its meters.",
               ["Fill in the form below and press **Create building**.",
                "Choose the new building in the left sidebar.",
                "Open **Meter Management** and add its meters so measurements can start."])
    st.caption("A new building has no measurements until it has meters.")
    if buildings:
        st.dataframe(pd.DataFrame(buildings), width="stretch")
    with st.form("add_building"):
        name = st.text_input("Building name", placeholder="Campus Sonnenstraße Dortmund",
                             help="Any name you will recognise, for example 'Main office'.")
        location = st.text_input("Location", placeholder="Sonnenstraße 96, 44139 Dortmund",
                             help="Town or address. Only used as a label.")
        area = st.number_input("Floor area (m²)", min_value=0.01, value=1000.0,
                               help="Size of the building in square metres.")
        baseline = st.number_input("Normal electricity use per day (kWh)", min_value=0.0, value=250.0,
                                   help="Roughly how much the building uses on a normal day. "
                                        "You get an alert when a day goes above this.")
        solar = st.checkbox("The building has solar panels", value=False)
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
            st.subheader("Meters of the selected building")
            if meters:
                st.dataframe(pd.DataFrame(meters), width="stretch", hide_index=True)
            else:
                st.info("No meters yet. Open **Meter Management** to add the first one.", icon=":material/electric_meter:")


def meter_management():
    st.header("Meter management")
    page_intro("A meter is the device that measures electricity. Without an active meter the app has nothing "
               "to show. A building needs **one active main meter**, plus **one solar meter** if it has solar panels.",
               ["Check the notice below to see if the setup is complete.",
                "Add missing meters at the bottom of the page.",
                "Switch a meter on or off with its button. Switching a main or solar meter off pauses measurements."])

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
        st.warning("Measurements are paused because the meter setup is incomplete. The building needs one active "
                   "main meter, and one active solar meter if (and only if) it has solar panels. "
                   "Add or switch on the missing meter below.", title="Setup incomplete")
    else:
        st.success("The meter setup is complete. A new meter starts reporting after its first full minute.",
                   title="Setup complete")

    st.subheader("Existing meters")

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

    st.subheader("Add New Meter")

    with st.form("add_meter_form"):
        device_id = st.text_input(
            "Meter Device ID",
            placeholder="METER-HVAC-002",
            help="A unique name for this meter, usually printed on the device."
        )

        meter_type = st.selectbox(
            "Meter Type",
            ["ELECTRICITY", "HVAC", "LIGHTING", "SOLAR"],
            help="ELECTRICITY = the main meter of the whole building. SOLAR = solar panels. "
                 "HVAC = heating and cooling. LIGHTING = lights."
        )

        is_active = st.checkbox(
            "Activate immediately",
            value=False,
            help="Switch the meter on straight away. You can also do it later."
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


def team_management():
    st.header("Team Management")
    page_intro("These are the people who can log in to this dashboard. **Admins** can manage the team; "
               "**Members** can use everything else.",
               ["Review the list of people below.",
                "To invite someone, fill in the form at the bottom. Give them a temporary password and tell "
                "them to use it for their first login."])

    users, err = all_rows("/accounts/users/")
    if show(err):
        return

    current_user_profile = st.session_state.get("auth_user") or {}
    current_username = current_user_profile.get("username", "admin") if isinstance(current_user_profile, dict) else "admin"

    st.subheader(f"Team Members ({len(users)})")
    if users:
        h1, h2, h3, h4 = st.columns([3, 3, 2, 2])
        h1.caption("**MEMBER**")
        h2.caption("**CONTACT & JOINED**")
        h3.caption("**ROLE**")
        h4.caption("**ACTIONS**")

        for u in users:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 3, 2, 2])

                full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                username_str = u.get("username", "")
                with c1:
                    if full_name:
                        st.markdown(f"**{full_name}**")
                        st.caption(f"@{username_str}")
                    else:
                        st.markdown(f"**@{username_str}**")
                        st.caption(f"ID #{u.get('id')}")

                with c2:
                    email_str = u.get("email")
                    st.markdown(email_str if email_str else "*No email*")
                    st.caption(f"Joined {str(u.get('date_joined', ''))[:10]}")

                with c3:
                    if u.get("is_staff"):
                        st.markdown("🛡️ **Admin**")
                    else:
                        st.markdown("👤 **Member**")

                with c4:
                    if username_str.lower() == "admin":
                        st.caption("*(System Admin)*")
                    elif username_str == current_username:
                        st.caption("*(Current Session)*")
                    else:
                        confirm_key = f"pending_delete_{u['id']}"
                        if st.session_state.get(confirm_key):
                            st.warning("Remove member?")
                            b1, b2 = st.columns(2)
                            if b1.button("Yes", key=f"yes_del_{u['id']}", type="primary", width="stretch"):
                                _, del_err = call("DELETE", f"/accounts/users/{u['id']}/")
                                st.session_state.pop(confirm_key, None)
                                if not show(del_err):
                                    st.success(f"Member '{username_str}' removed.")
                                    st.rerun()
                            if b2.button("No", key=f"no_del_{u['id']}", width="stretch"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        else:
                            if st.button("Delete", key=f"del_user_{u['id']}", width="stretch"):
                                st.session_state[confirm_key] = True
                                st.rerun()
    else:
        st.info("No team members found.")

    st.divider()

    with st.container(border=True):
        st.subheader("Add a Member")
        with st.form("add_member_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_u = st.text_input("Username *", key="team_member_username")
                new_e = st.text_input("Email", key="team_member_email")
            with col2:
                new_p = st.text_input("Temporary Password *", type="password", key="team_member_password")
                new_fn = st.text_input("First Name", key="team_member_fn")
                new_ln = st.text_input("Last Name", key="team_member_ln")

            st.caption("Enter a temporary password for the member to log in.")
            submit_btn = st.form_submit_button("Add Member", type="primary")

            if submit_btn:
                u_clean = new_u.strip()
                p_clean = new_p.strip()
                if not u_clean or not p_clean:
                    st.error("Username and temporary password are required.")
                else:
                    payload = {
                        "username": u_clean,
                        "password": p_clean,
                        "email": new_e.strip(),
                        "first_name": new_fn.strip(),
                        "last_name": new_ln.strip(),
                    }
                    _, err = call("POST", "/accounts/users/", json=payload)
                    if not show(err):
                        st.success(f"Team member '{u_clean}' added successfully!")
                        st.rerun()


# --- S3: costs, scenarios, alerts, reports ----------------------------------
# Plain-language explanations for the machine-readable reason codes the API returns.
REASONS = {
    "missing_active_tariff": "No tariff is active yet. Create one on the Costs page first.",
    "ambiguous_active_tariffs": "More than one tariff is active. Keep exactly one active on the Costs page.",
    "invalid_tariff": "The active tariff has invalid values. Edit or replace it on the Costs page.",
    "missing_readings": "There are no meter readings for this building yet.",
    "no_readings": "There are no meter readings for this building yet.",
    "unknown_duration": "Some readings have no interval length, so energy cannot be priced exactly.",
    "unknown_duration_before_window": "Some readings before the period have no interval length.",
    "overlapping_intervals": "Readings overlap in time, so they cannot be added up safely.",
    "main_solar_intervals_do_not_match": "Solar and main-meter readings do not cover the same time slots.",
    "interval_crosses_tariff_band": "A reading spans both a standard and a peak price period, so it cannot be "
                                    "priced exactly. Use finer readings or a flat tariff (same standard and peak rate).",
    "coverage_incomplete": "Some of the selected days are missing measurements. Open \"More options\" and "
                           "choose \"Latest complete days\", or pick days that were measured completely.",
    "period_not_fully_covered": "Every hour of the selected days needs readings. Pick fully recorded days.",
    "period_start_after_period_end": "The start date is after the end date.",
}

ALERT_HELP = {
    "PEAK_SPIKE": "The latest power reading is more than twice the 24-hour average. "
                  "Check for equipment that was switched on all at once.",
    "UNUSUAL_NIGHT_LOAD": "The building uses a lot of power at night (00:00-05:00 UTC). "
                          "Check for devices that were left running.",
    "METER_OFFLINE": "A meter has not sent data for over 15 minutes. Check its power and network connection.",
    "BUDGET_EXCEEDED": "Yesterday's consumption was above the building's daily baseline. "
                       "Review the Recommendations page for ways to reduce it.",
}

SEVERITY_BADGE = {"CRITICAL": ("Critical", "red", ":material/error:"),
                  "WARNING": ("Warning", "orange", ":material/warning:")}


def explain(reason):
    return REASONS.get(reason, f"Not available ({reason}).")


def active_tariffs():
    data, err = call("GET", "/tariffs/")
    if err:
        return None, err
    return [t for t in results(data) if t["is_active"]], None


def _switch_tariff(new_id, old_ids):
    """Make `new_id` the only active tariff. The API allows one active tariff at a time."""
    for old_id in old_ids:
        _, err = call("PATCH", f"/tariffs/{old_id}/", json={"is_active": False})
        if err:
            return err
    _, err = call("PATCH", f"/tariffs/{new_id}/", json={"is_active": True})
    return err


def _price_text(tariff):
    standard, peak = tariff["rate_standard_eur_per_kwh"], tariff["rate_peak_eur_per_kwh"]
    if standard == peak:
        return f"**{standard:.2f} EUR per kWh**, at any time of day."
    return (f"**{standard:.2f} EUR per kWh** normally, and **{peak:.2f} EUR per kWh** between "
            f"{tariff['peak_start_hour']:02d}:00 and {tariff['peak_end_hour']:02d}:00 (UTC).")


def _tariff_editor(active, first=False):
    """Simple price form. Saving switches to the new price in one step."""
    name = st.text_input("Name of the price plan", "Gewerbestrom Standard (Dortmund)" if first else "My new price",
                         key="tf_name", help="Only a label, for example the name on your electricity bill.")
    price = st.number_input("Price per kWh (EUR)", 0.0, 5.0, value=0.30, step=0.01, format="%.2f", key="tf_price",
                            help="You can find this on your electricity bill. In Germany it is usually 0.25-0.40 EUR.")
    peak = price
    start_hour, end_hour = 11, 16
    if st.toggle("Electricity costs more at busy times of the day", key="tf_has_peak"):
        cols = st.columns(3)
        peak = cols[0].number_input("Busy-time price (EUR/kWh)", 0.0, 5.0, value=round(price + 0.10, 2), step=0.01,
                                    format="%.2f", key="tf_peak")
        start_hour = cols[1].number_input("Busy time starts (hour, UTC)", 0, 23, 11, key="tf_start")
        end_hour = cols[2].number_input("Busy time ends (hour, UTC)", 0, 23, 16, key="tf_end")
    feed_in = st.number_input("Money you get per kWh of solar sent to the grid (EUR)", 0.0, 5.0, value=0.08,
                              step=0.01, format="%.2f", key="tf_feed",
                              help="Called the feed-in tariff (Einspeisevergütung). Use 0 if you have no solar panels.")
    if st.button("Save price", type="primary", icon=":material/save:", key="tf_save"):
        if start_hour == end_hour:
            st.error("The busy time must start and end at different hours.")
            return
        body = {"name": name.strip() or "My price", "rate_standard_eur_per_kwh": price,
                "rate_peak_eur_per_kwh": peak, "peak_start_hour": int(start_hour),
                "peak_end_hour": int(end_hour), "solar_feed_in_eur_per_kwh": feed_in,
                "is_active": not active}
        created, err = call("POST", "/tariffs/", json=body)
        if show(err):
            return
        if active:
            if show(_switch_tariff(created["id"], [t["id"] for t in active])):
                return
        st.success("Price saved. Your costs are now calculated with it.", icon=":material/check_circle:")
        st.rerun()


def _cost_explanation():
    """Button that asks the backend (OpenAI, or built-in rules) to explain the costs in plain words."""
    key = f"cost_explanation_{building_id}"
    with st.container(border=True):
        st.markdown("#### :material/auto_awesome: Explain my costs in simple words")
        st.caption("An AI assistant reads your numbers and explains them, with tips to pay less.")
        if st.button("Explain my costs", icon=":material/auto_awesome:", key="explain_costs"):
            with st.spinner("Writing your explanation..."):
                answer, err = call("POST", f"/buildings/{building_id}/cost/explain/", json={})
            if not show(err):
                st.session_state[key] = answer
        answer = st.session_state.get(key)
        if not answer:
            return
        if not answer.get("available"):
            st.info(explain(answer.get("reason")), icon=":material/info:")
            return
        st.write(answer["text"])
        if answer["source"] == "OPENAI":
            st.caption(":material/smart_toy: Written by AI (OpenAI). Check important numbers above.")
        elif answer.get("fallback_reason"):
            st.caption(":material/rule: The AI could not be reached, so the app's built-in rules wrote this.")
        else:
            st.caption(":material/rule: Written by the app's built-in rules (no AI key is set up).")


def costs():
    st.header("Costs")
    st.write("How much this building's electricity costs, worked out from its meter readings "
             "and the price you pay per kWh.")
    data, err = call("GET", "/tariffs/")
    if show(err):
        return
    active = [t for t in results(data) if t["is_active"]]

    if not active:
        st.info("Tell the app what you pay for electricity and it will work out your costs. "
                "The suggested values are typical for a business in Dortmund.",
                title="Step 1: enter your electricity price", icon=":material/payments:")
        with st.container(border=True):
            _tariff_editor(active, first=True)
        return
    if len(active) > 1:
        st.warning("More than one price is switched on. Choose the one you really pay.",
                   title="Choose one price", icon=":material/rule:")
        for tariff in active:
            if st.button(f"Use '{tariff['name']}'", key=f"keep{tariff['id']}"):
                if not show(_switch_tariff(tariff["id"], [t["id"] for t in active if t["id"] != tariff["id"]])):
                    st.rerun()
        return
    tariff = active[0]

    cost, err = call("GET", f"/buildings/{building_id}/cost/")
    if show(err):
        return
    cost = cost if isinstance(cost, dict) else {}
    if cost.get("cost_estimates_available"):
        summary, _ = call("GET", f"/buildings/{building_id}/summary/")
        summary = summary if isinstance(summary, dict) else {}
        first, last = summary.get("earliest_reading"), summary.get("latest_reading")
        days = None
        if first and last:
            days = max((pd.to_datetime(last) - pd.to_datetime(first)).total_seconds() / 86400, 1 / 24)
        net = cost["estimated_net_cost_eur"]
        with st.container(border=True):
            st.markdown(f"### You paid about **{net:,.2f} EUR** for electricity")
            if first and last:
                st.caption(f":material/date_range: From {pd.to_datetime(first):%d %b %Y} to "
                           f"{pd.to_datetime(last):%d %b %Y}, since the meters started measuring.")
            cols = st.columns(3)
            with cols[0]:
                metric("Average per day", net / days if days else None, " EUR",
                       help="Total cost divided by the number of days measured.")
            with cols[1]:
                metric("Electricity bought", cost["estimated_grid_import_kwh"], " kWh",
                       help="Electricity that came from the grid, after your own solar power was used.")
            with cols[2]:
                metric("Earned from solar", cost["estimated_export_credit_eur"], " EUR",
                       help="Money for surplus solar power sent back to the grid.")

        st.subheader("Where the money goes")
        st.markdown(
            "| | Energy | Money |\n|---|---:|---:|\n"
            f"| :material/bolt: Electricity bought from the grid | {cost['estimated_grid_import_kwh']:,.1f} kWh "
            f"| {cost['estimated_import_cost_eur']:,.2f} EUR |\n"
            f"| :material/solar_power: Solar surplus sent back to the grid | {cost['estimated_grid_export_kwh']:,.1f} kWh "
            f"| - {cost['estimated_export_credit_eur']:,.2f} EUR |\n"
            f"| **You pay** | | **{net:,.2f} EUR** |")
        st.caption("Solar power you use yourself is free, so it does not appear on the bill. "
                   "This is an estimate for planning, not an invoice.")
        scenarios_target = globals().get("scenarios_page")
        if scenarios_target is not None:
            st.page_link(scenarios_target, label="Want to pay less? Try an idea on the \"What if...?\" page",
                         icon=":material/savings:")
        _cost_explanation()
    else:
        st.info(explain(cost.get("cost_estimates_reason", "missing_readings")),
                title="Costs can't be calculated yet", icon=":material/info:")

    st.subheader("Your electricity price")
    with st.container(border=True):
        st.markdown(f":material/sell: {_price_text(tariff)}")
        st.markdown(f":material/solar_power: You get **{tariff['solar_feed_in_eur_per_kwh']:.2f} EUR** "
                    f"for every kWh of solar power you send to the grid.")
        st.caption(f"Price plan: {tariff['name']}")
    with st.expander("Change my electricity price", icon=":material/edit:"):
        st.caption("Enter the new price. The old one is switched off automatically.")
        _tariff_editor(active)


SCENARIO_IDEAS = {
    "Use less electricity": ":material/power_settings_new:",
    "Get more solar power": ":material/solar_power:",
    "Switch to a cheaper tariff": ":material/sell:",
}


def scenarios():
    st.header("What if...?")
    st.write("Try one idea and see straight away how much money it would have saved. "
             "This is only a calculation. Nothing in your building or your tariff is changed.")

    active, err = active_tariffs()
    if show(err):
        return
    if len(active) != 1:
        st.warning(explain("missing_active_tariff" if not active else "ambiguous_active_tariffs"),
                   title="A tariff is needed first", icon=":material/payments:")
        return
    tariff = active[0]

    idea = st.segmented_control(
        "What would you like to try?", list(SCENARIO_IDEAS), default="Use less electricity",
        format_func=lambda name: f"{SCENARIO_IDEAS[name]} {name}", key="sc_idea")
    idea = idea or "Use less electricity"

    body = {"consumption_change_pct": 0, "solar_change_pct": 0}
    with st.container(border=True):
        if idea == "Use less electricity":
            amount = st.slider("How much less electricity?", 0, 50, 10, step=5, format="%d%%", key="sc_less",
                               help="For example: switch off lights in empty rooms, turn the heating down a little.")
            body["consumption_change_pct"] = -amount
            what = f"used {amount}% less electricity"
        elif idea == "Get more solar power":
            amount = st.slider("How much more solar power?", 0, 100, 20, step=10, format="%d%%", key="sc_more_solar",
                               help="For example: 20% means adding about one fifth more solar panels.")
            body["solar_change_pct"] = amount
            what = f"had {amount}% more solar power"
        else:
            current = float(tariff["rate_standard_eur_per_kwh"])
            st.caption(f"Your current price: **{current:.2f} EUR per kWh** ({tariff['name']}).")
            price = st.number_input("New price per kWh (EUR)", 0.0, 2.0, value=round(max(current - 0.05, 0.0), 2),
                                    step=0.01, format="%.2f", key="sc_price",
                                    help="The price per kWh offered by the other supplier.")
            body["tariff"] = {"name": "Other tariff", "rate_standard_eur_per_kwh": price,
                              "rate_peak_eur_per_kwh": price, "peak_start_hour": tariff["peak_start_hour"],
                              "peak_end_hour": tariff["peak_end_hour"],
                              "solar_feed_in_eur_per_kwh": tariff["solar_feed_in_eur_per_kwh"]}
            what = f"paid {price:.2f} EUR per kWh"

    with st.expander("More options: choose the time period"):
        st.caption("By default the calculation uses the most recent days that were measured completely.")
        mode = st.segmented_control("Time period", ["Latest complete days", "Choose dates"],
                                    default="Latest complete days", key="sc_mode")
        if mode == "Choose dates":
            summary, _ = call("GET", f"/buildings/{building_id}/summary/")
            first = (summary or {}).get("earliest_reading") or (summary or {}).get("latest_reading")
            last = (summary or {}).get("latest_reading")
            lo = pd.to_datetime(first).date() if first else date.today() - timedelta(days=14)
            hi = pd.to_datetime(last).date() if last else date.today()
            st.caption(f"Measurements exist from {lo} to {hi}.")
            dcols = st.columns(2)
            start = dcols[0].date_input("From", lo, key="sc_start")
            end = dcols[1].date_input("To", hi, key="sc_end")
            if start > end:
                st.error("The start date must not be after the end date.")
                return
            body.update(period_start=str(start), period_end=str(end))

    data, err = call("POST", f"/buildings/{building_id}/scenarios/", json=body)
    if show(err):
        return
    if not data["available"]:
        st.warning(explain(data["reason"]), title="This can't be calculated yet", icon=":material/info:")
        return

    base, scen = data["baseline"], data["scenario"]
    diff = data["difference_net_cost_eur"]
    share = abs(diff) / base["net_cost_eur"] * 100 if base["net_cost_eur"] else None
    share_text = f" (about {share:.0f}% of your bill)" if share else ""
    if diff < 0:
        st.success(f"If you {what}, you would have **saved {abs(diff):,.2f} EUR**{share_text}.",
                   icon=":material/savings:")
    elif diff > 0:
        st.error(f"If you {what}, you would have **paid {diff:,.2f} EUR more**{share_text}.",
                 icon=":material/trending_up:")
    else:
        st.info(f"If you {what}, your cost would stay the same.", icon=":material/drag_handle:")

    with st.container(border=True):
        cols = st.columns(3)
        with cols[0]:
            metric("What you paid", base["net_cost_eur"], " EUR",
                   help="Cost of the recorded electricity with your tariff.")
        with cols[1]:
            metric("With this idea", scen["net_cost_eur"], " EUR",
                   help="The same period, re-calculated with your idea.")
        with cols[2]:
            st.metric("Difference", f"{diff:+,.2f} EUR", delta=f"{diff:+,.2f} EUR", delta_color="inverse",
                      help="Negative (green) means the idea saves money.")
    if data.get("period_start"):
        days = (date.fromisoformat(data["period_end"]) - date.fromisoformat(data["period_start"])).days + 1
        st.caption(f":material/date_range: Calculated for {data['period_start']} to {data['period_end']} "
                   f"({days} complete day{'s' if days != 1 else ''}).")
    st.caption("Estimate based on your recorded measurements. No battery is assumed. Not an invoice.")


def alerts():
    st.header("Alerts")
    st.write("Alerts warn you about unusual energy use or a meter that stopped reporting. "
             "Press **Check for new alerts** to scan the latest data. Resolve an alert once you have dealt with it.")
    if st.button("Check for new alerts", type="primary", icon=":material/search:"):
        data, err = call("POST", "/alerts/detect/", json={"building_id": building_id})
        if not show(err):
            n = data["created_count"]
            st.success(f"{n} new alert(s) found." if n else "No new problems found. Everything looks normal.")
    only_open = st.toggle("Show only open alerts", True)
    params = {"building_id": building_id}
    if only_open:
        params["is_resolved"] = "false"
    data, err = call("GET", "/alerts/", params=params)
    if show(err):
        return
    rows = results(data)
    if not rows:
        st.info("No alerts to show. That is good news.", icon=":material/check_circle:")
        return
    order = {"CRITICAL": 0, "WARNING": 1}
    for alert in sorted(rows, key=lambda a: order.get(a["severity"], 2)):
        label, color, icon = SEVERITY_BADGE.get(alert["severity"], (alert["severity"].title(), "blue", ":material/info:"))
        with st.container(border=True):
            top = st.columns([5, 1], vertical_alignment="center")
            top[0].markdown(f":{color}-badge[{icon} {label}] **{alert['alert_type_display']}**")
            if alert["is_resolved"]:
                top[1].caption("Resolved")
            elif top[1].button("Mark resolved", key=f"r{alert['id']}", width="stretch"):
                _, err = call("PATCH", f"/alerts/{alert['id']}/", json={"is_resolved": True})
                if not show(err):
                    st.rerun()
            st.write(alert["message"])
            st.caption(f"Detected {alert['created_at']}")
            hint = ALERT_HELP.get(alert["alert_type"])
            if hint:
                with st.expander("What does this mean?"):
                    st.write(hint)


def reports():
    st.header("Cost reports")
    st.write("A report saves the cost of one fixed period, such as last week, so you can look it up later. "
             "Pick days that have complete readings.")
    yesterday = date.today() - timedelta(days=1)
    cols = st.columns(2)
    start = cols[0].date_input("From (UTC, inclusive)", yesterday)
    end = cols[1].date_input("To (UTC, inclusive)", yesterday)
    if st.button("Generate report", type="primary", icon=":material/description:"):
        if start > end:
            st.error("The start date must not be after the end date.")
        else:
            data, err = call("POST", f"/buildings/{building_id}/reports/",
                             json={"period_start": str(start), "period_end": str(end)})
            if err and isinstance(data, dict) and "reason" in data:
                st.warning(explain(data["reason"]), title="Report could not be created", icon=":material/info:")
            elif not show(err):
                st.success("Report saved. You can find it in the table below.")
    st.subheader("Saved reports")
    data, err = call("GET", f"/buildings/{building_id}/reports/")
    rows = results(data) if not err else []
    if show(err):
        return
    if not rows:
        st.info("No reports yet. A report needs an active tariff and days with complete readings.",
                icon=":material/description:")
        return
    frame = pd.DataFrame(rows)
    shown = frame[["period_start", "period_end", "total_grid_kwh", "total_cost_eur", "solar_savings_eur",
                   "created_at"]]
    st.dataframe(shown, width="stretch", hide_index=True, column_config={
        "period_start": "From", "period_end": "To",
        "total_grid_kwh": st.column_config.NumberColumn("Grid energy (kWh)", format="%.2f"),
        "total_cost_eur": st.column_config.NumberColumn("Net cost (EUR)", format="%.2f"),
        "solar_savings_eur": st.column_config.NumberColumn("Solar savings (EUR)", format="%.2f"),
        "created_at": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm")})
    st.download_button("Download as CSV", shown.to_csv(index=False), "cost_reports.csv", "text/csv",
                       icon=":material/download:")


def forecast():
    st.header("Forecast")
    page_intro("A forecast is an educated guess of how much electricity the building will use over the next "
               "7 days, based on its recent days. It is a rough guide, not a promise.",
               ["Wait until the building has at least two full days of measurements.",
                "Read the two numbers: the total expected over 7 days and the average per day.",
                "In the chart, the middle line is the best guess; the other two lines show a likely range."])
    data, err = call("GET", f"/buildings/{building_id}/forecast/")
    if show(err):
        return
    rows = data.get("forecast") or []
    if not rows:
        reason = (data.get("availability") or {}).get("reason", "unknown")
        st.info(reason_text(reason) + " A forecast needs at least two complete days of measurements.",
                title="No forecast yet", icon=":material/timeline:")
    else:
        cols = st.columns(2)
        with cols[0]:
            metric("Expected use, next 7 days", data["total_predicted_7d_kwh"], " kWh",
                   help="Best guess of the total electricity the building will use in the next week.")
        with cols[1]:
            metric("Expected use per day", data["avg_daily_predicted_kwh"], " kWh",
                   help="The 7-day total divided by 7.")
        frame = pd.DataFrame(rows)
        frame["forecast_date"] = pd.to_datetime(frame["forecast_date"])
        st.line_chart(frame.set_index("forecast_date")[
            ["predicted_kwh", "confidence_lower_kwh", "confidence_upper_kwh"]].rename(columns={
                "predicted_kwh": "Best guess", "confidence_lower_kwh": "Low estimate",
                "confidence_upper_kwh": "High estimate"}))
        st.dataframe(frame[["forecast_date", "predicted_kwh", "confidence_lower_kwh",
                            "confidence_upper_kwh", "trend"]], width="stretch", hide_index=True,
                     column_config={"forecast_date": "Day", "predicted_kwh": "Best guess (kWh)",
                                    "confidence_lower_kwh": "Low (kWh)", "confidence_upper_kwh": "High (kWh)",
                                    "trend": "Trend"})
    with st.expander("Technical details"):
        st.json(data.get("availability") or {})


def recommendations():
    st.header("Recommendations")
    page_intro("Tips for using less electricity, written by an AI assistant from your building's own data. "
               "If the AI service is not available, built-in rules give the tips instead.",
               ["Choose how much energy you would like to save.",
                "Press **Generate recommendations**.",
                "Read each tip. After you try one, rate it so the app learns what is useful."])
    target = st.slider("How much would you like to save? (%)", 1, 50, 15,
                       help="Your goal. The tips aim at this saving but cannot guarantee it.")
    if st.button("Generate recommendations"):
        data, err = call("POST", "/recommendations/generate/",
                         json={"building_id": building_id, "target_savings_pct": target})
        if show(err):
            return
        availability = data.get("availability") or {}
        if not availability.get("available"):
            st.info(reason_text(availability.get("reason")) + " Tips need a few complete days of measurements.",
                    title="Not enough data yet", icon=":material/lightbulb:")
        else:
            st.success(f"{len(data.get('recommendations', []))} recommendation(s) stored "
                       f"(engine: {data['engine_telemetry']['source']}).")
        with st.expander("Technical details: sustainability assessment"):
            st.json(data.get("sustainability_assessment") or {})
    st.subheader("Your saved tips")
    data, err = call("GET", "/recommendations/", params={"building_id": building_id})
    if show(err):
        return
    rows = results(data)
    if not rows:
        st.info("No tips yet. Press **Generate recommendations** above once the building has a few full days "
                "of measurements.", icon=":material/lightbulb:")
    for rec in rows:
        with st.container(border=True):
            st.markdown(f"**{rec['title']}**  \n{rec['category_display']} | priority "
                        f"{rec['priority_display']} | source {rec['source']} | status {rec['status']}")
            st.write(rec["suggested_action"])
            st.caption(f"Estimated saving: {rec['estimated_savings_kwh']} kWh | "
                       f"confidence: {rec['confidence_score']}")
            with st.form(f"feedback{rec['id']}"):
                rating = st.slider("How useful was this tip? (1 = not, 5 = very)", 1, 5, 5, key=f"rate{rec['id']}")
                accepted = st.checkbox("I will follow this tip", True, key=f"acc{rec['id']}")
                comment = st.text_input("Comment (optional)", key=f"com{rec['id']}")
                if st.form_submit_button("Send feedback"):
                    _, err = call("POST", f"/recommendations/{rec['id']}/feedback/",
                                  json={"rating": rating, "is_accepted": accepted, "comment": comment})
                    if not show(err):
                        st.success("Feedback stored.")


# --- navigation & routing --------------------------------------------------
if "auth_token" not in st.session_state:
    login_page = st.Page(login_screen, title="Log In", icon=":material/login:", url_path="login", default=True)
    overview_page = st.Page(login_screen, title="Overview", url_path="overview")
    building_page = st.Page(login_screen, title="Building Management", url_path="building-management")
    meter_page = st.Page(login_screen, title="Meter Management", url_path="meter-management")
    team_page = st.Page(login_screen, title="Team Management", url_path="team-management")
    costs_page = st.Page(login_screen, title="Costs", url_path="costs")
    scenarios_page = st.Page(login_screen, title="Scenarios", url_path="scenarios")
    alerts_page = st.Page(login_screen, title="Alerts", url_path="alerts")
    reports_page = st.Page(login_screen, title="Reports", url_path="reports")
    forecast_page = st.Page(login_screen, title="Forecast", url_path="forecast")
    recommendations_page = st.Page(login_screen, title="Recommendations", url_path="recommendations")

    pg = st.navigation([
        login_page,
        overview_page,
        building_page,
        meter_page,
        team_page,
        costs_page,
        scenarios_page,
        alerts_page,
        reports_page,
        forecast_page,
        recommendations_page,
    ], position="hidden")
    pg.run()
else:
    overview_page = st.Page(overview, title="Overview", icon=":material/dashboard:", url_path="overview", default=True)
    building_page = st.Page(building_management, title="Building Management", icon=":material/apartment:", url_path="building-management")
    meter_page = st.Page(meter_management, title="Meter Management", icon=":material/electric_meter:", url_path="meter-management")
    team_page = st.Page(team_management, title="Team Management", icon=":material/group:", url_path="team-management")
    costs_page = st.Page(costs, title="Costs", icon=":material/payments:", url_path="costs")
    scenarios_page = st.Page(scenarios, title="Scenarios", icon=":material/science:", url_path="scenarios")
    alerts_page = st.Page(alerts, title="Alerts", icon=":material/warning:", url_path="alerts")
    reports_page = st.Page(reports, title="Reports", icon=":material/description:", url_path="reports")
    forecast_page = st.Page(forecast, title="Forecast", icon=":material/timeline:", url_path="forecast")
    recommendations_page = st.Page(recommendations, title="Recommendations", icon=":material/lightbulb:", url_path="recommendations")

    pg = st.navigation({
        "Monitor": [overview_page, alerts_page],
        "Money": [costs_page, scenarios_page, reports_page],
        "Plan and save": [forecast_page, recommendations_page],
        "Set up": [building_page, meter_page, team_page],
    })

    st.logo(str(ASSETS / "logo.svg"), size="large")
    st.sidebar.title("Smart Energy")
    user = st.session_state.get("auth_user", {})
    username = user.get("username", "admin") if isinstance(user, dict) else "admin"
    st.sidebar.caption(f":bust_in_silhouette: Logged in as: **{username}**")
    if st.sidebar.button("Log out", key="logout_btn", width="stretch"):
        _SESSION_CACHE.clear()
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    buildings, err = all_rows("/buildings/")
    show(err)
    options = {f"{b['name']} (#{b['id']})": b["id"] for b in buildings}
    building_id = options[st.sidebar.selectbox(
        "Building", list(options), help="Every page shows data for the building chosen here.")] if options else None
    if st.sidebar.button("Refresh", help="Load the newest data."):
        st.rerun()
    with st.sidebar.expander("What can I do here?", icon=":material/help:"):
        st.markdown("- **Monitor**: see how much electricity is used and get warned about problems.\n"
                    "- **Money**: see what it costs, try \"what if\" ideas and save reports.\n"
                    "- **Plan and save**: see a 7-day forecast and get tips to save energy.\n"
                    "- **Set up**: add buildings, meters and team members.")
    with st.sidebar.expander("Words explained", icon=":material/menu_book:"):
        for term, meaning in GLOSSARY.items():
            st.markdown(f"**{term}**  \n{meaning}")
    st.sidebar.caption(f"API: {API}")

    if building_id is None and pg.title not in ("Building Management", "Team Management"):
        st.info("No building selected yet. Open **Building Management** in the sidebar to add your first building.",
                icon=":material/apartment:")
    else:
        pg.run()
