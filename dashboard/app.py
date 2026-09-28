"""Container Hub dashboard. Credentials stay in the server-side session."""
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import streamlit as st
from html import escape

API_URL = os.environ.get("MONITOR_API_URL", "http://ai-monitor:8090").rstrip("/")
st.set_page_config(page_title="Container Hub · Monitor", page_icon=":material/deployed_code:", layout="wide")

class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def api(path, body=None):
    headers = {"Content-Type": "application/json"}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API_URL + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(request, timeout=45) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            message = json.load(error).get("message", "Request failed.")
        except (ValueError, OSError):
            message = "Request failed."
        raise RequestError(error.code, message) from None
    except (URLError, OSError, ValueError):
        raise RequestError(503, "Cannot reach the monitoring service. Try again shortly.") from None

def handle_error(error):
    if error.status == 401:
        st.session_state.clear()
        st.session_state["signed_out_message"] = error.message
        st.rerun()
    st.error(error.message)

def sign_out():
    try:
        api("/logout", {})
    except RequestError:
        pass
    st.session_state.clear()
    st.rerun()

def timestamp(value):
    try:
        parsed = datetime.fromtimestamp(value, timezone.utc) if isinstance(value, (int, float)) else datetime.fromisoformat(value)
        return parsed.strftime("%d %b %Y · %H:%M UTC")
    except (ValueError, TypeError):
        return "Waiting for first collection"

def show_analysis(job):
    status = job.get("status", "waiting")
    if status == "running":
        st.info("Analysis is " + status + ". This view refreshes automatically.", icon=":material/schedule:")
    elif status == "ready":
        result = job["result"]
        for label, key in (("Summary", "summary"), ("Possible cause", "possible_cause"),
                           ("Suggested checks", "suggested_checks"), ("Uncertainty", "uncertainty")):
            st.markdown("**" + label + "**")
            st.text(result["output"].get(key, "Not provided"))
        st.caption("Generated " + timestamp(result["created_at"]) + " · " + str(result["model"]))
        st.caption("Advisory analysis. No changes were made to the container.")
    else:
        st.warning(job.get("error") or "Analysis is not available yet.")



if not st.session_state.get("token"):
    with st.container(horizontal_alignment="center"):
        with st.container(width=470):
            with st.container(horizontal_alignment="center"):
                st.image(
                    os.path.join(
                        os.path.dirname(__file__),
                        "assets",
                        "logo.jpg",
                    ),
                    width=280,
                )

            st.space("small")

            with st.form("sign_in", clear_on_submit=True):
                st.subheader("Sign in")
                st.caption(
                    "Sign in with a Portainer administrator account "
                )

                username = st.text_input(
                    "Username",
                    autocomplete="username",
                )
                password = st.text_input(
                    "Password",
                    type="password",
                    autocomplete="password",
                )

                submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    width="stretch",
                )

            if st.session_state.get("signed_out_message"):
                st.info(st.session_state.pop("signed_out_message"))

            if submitted:
                try:
                    result = api(
                        "/login",
                        {"username": username, "password": password},
                    )
                    st.session_state["token"] = result["token"]
                    st.session_state["username"] = result["username"]
                    st.rerun()
                except RequestError as error:
                    message = error.message
                    if message == "Portainer is unavailable.":
                        message = "Unable to connect to the service. Please try again shortly."
                    st.error(message)

            

    st.stop()


@st.fragment(run_every=10)
def workspace():
    st.html("""
    <style>
        .stApp {
            background: #F3F7FC;
        }

        .st-key-hub_header {
            background: linear-gradient(
                110deg, #FFFFFF 25%, #EDF8FF 75%, #E5EFFF 100%
            );
            border: 1px solid #D9E7F5;
            border-top: 3px solid #159EEB;
            border-radius: 20px;
            padding: 18px 24px;
            box-shadow: 0 6px 24px rgba(16, 52, 100, 0.05);
        }

        .st-key-hub_actions {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #DCE7F4;
            border-radius: 16px;
            padding: 10px 14px;
        }

        .hub-account {
            display: flex;
            align-items: center;
            gap: 10px;
            padding-right: 12px;
            border-right: 1px solid #DCE7F4;
        }

        .hub-avatar {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 38px;
            height: 38px;
            flex-shrink: 0;
            border-radius: 50%;
            background: linear-gradient(135deg, #09B7EC, #2563EB);
            color: white;
            font-size: 16px;
            font-weight: 700;
        }

        .hub-account-label {
            color: #64748B;
            font-size: 11px;
            line-height: 1.4;
        }

        .hub-account-name {
            color: #14213D;
            font-size: 15px;
            font-weight: 650;
            line-height: 1.5;
            overflow-wrap: anywhere;
            max-width: 180px;
        }

        .st-key-hub_actions button {
            border-radius: 10px;
        }

        [data-testid="stMetric"] {
            background: #FFFFFF;
            border-radius: 14px;
        }
    </style>
    """)

    username = str(st.session_state.get("username") or "User")
    safe_username = escape(username)
    initial = escape(username[:1].upper())

    with st.container(key="hub_header"):
        brand_col, actions_col = st.columns(
            [1, 3],
            vertical_alignment="center",
        )

        with brand_col:
            st.image(
                os.path.join(
                    os.path.dirname(__file__),
                    "assets",
                    "logo.jpg",
                ),
                width=115,
            )

        with actions_col:
            with st.container(horizontal_alignment="right"):
                with st.container(
                    key="hub_actions",
                    width="content",
                    horizontal=True,
                    vertical_alignment="center",
                    gap="small",
                ):
                    with st.container(width="content"):
                        st.html(
                            f'<div class="hub-account">'
                            f'<div class="hub-avatar">{initial}</div>'
                            f'<div>'
                            f'<div class="hub-account-label">ACCOUNT</div>'
                            f'<div class="hub-account-name">{safe_username}</div>'
                            f'</div>'
                            f'</div>'
                        )

                    if st.button(
                        "Sign out",
                        icon=":material/logout:",
                        key="header_sign_out",
                        width="content",
                    ):
                        sign_out()

                    notifications_area = st.container(width="content")

    st.space("small")
    st.title("Container monitoring")
    st.caption("Rules monitor continuously. AI runs only when you select Analyze with AI.")
    try:
        account = api("/environments")
    except RequestError as error:
        handle_error(error)
        return
    envs = account["environments"]
    if not envs:
        st.info("No supported Docker environments are available to this account.")
        return
    envmap = {e["id"]: e["name"] for e in envs}
    with st.container(horizontal=True, vertical_alignment="bottom"):
        eid = st.selectbox("Environment", list(envmap), format_func=envmap.get, width=320)
        st.button("Refresh", icon=":material/refresh:", key="refresh")
    try:
        report = api(f"/report?environment={eid}")
    except RequestError as error:
        handle_error(error)
        return
    containers = report.get("containers", [])
    notices = report.get("notices", [])
    unread = [n for n in notices if n["unread"]]
    status = report.get("collection_status", "starting")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(report["checked_at"])).total_seconds()
    except (KeyError, ValueError):
        age = None
    fresh = age is not None and -10 <= age <= 150
    collector_ok = report.get("collector", {}).get("status") == "ok"
    with st.container(horizontal=True, vertical_alignment="center"):
        ai_status = report.get("ai_status", {}).get("status", "on_demand")
        st.badge(
            "AI · " + ai_status.replace("_", " "),
            color="blue" if ai_status == "on_demand" else "gray",
        )
        telegram_status = report.get("telegram_status", {}).get("status", "not_configured")
        st.badge("Telegram · " + telegram_status.replace("_", " "),
                 color="green" if telegram_status == "ready" else "gray")
        st.caption("Updated " + timestamp(report.get("checked_at")))

    with notifications_area:
        with st.popover(f"Notifications · {len(unread)}", icon=":material/notifications:"):
            if not notices:
                st.caption("No notifications for your current container access.")
            if unread and st.button("Mark all as read", key=f"readall:{eid}"):
                try:
                    api(f"/notices/read?environment={eid}", {"ids": [n["id"] for n in unread]})
                    st.rerun(scope="fragment")
                except RequestError as error:
                    handle_error(error)
            for notice in notices[:30]:
                with st.container(border=True):
                    st.text(notice["title"])
                    st.caption(notice["body"].get("container_name", "") + " · " + timestamp(notice["updated"]))
                    st.caption(("Unread · " if notice["unread"] else "") +
                               ("Container lifecycle" if notice["kind"] == "lifecycle" else "Rule match"))
                    st.code("\n".join(notice["body"].get("evidence", [])), language="text")
    if not fresh and status != "starting":
        st.warning("Collection is stale or its clock is incorrect. Container values below may be out of date.")
    if not collector_ok:
        st.warning("The monitor cannot currently collect from Portainer. Existing values are historical.")
    if status in ("failed", "starting"):
        st.info("Waiting for a monitoring sample." if status == "starting" else
                report.get("collection_error", "Collection failed."))
    elif status == "partial":
        st.warning("Some observations could not be collected. See the affected containers.")
    with st.container(horizontal=True):
        st.metric("Visible containers", len(containers), border=True)
        st.metric("Running" if fresh else "Last observed running", sum(c.get("state") == "running" for c in containers), border=True)

    st.subheader("All containers")

    search = st.text_input(
        "Search containers",
        placeholder="Search by container name",
        icon=":material/search:",
    )

    visible = [
        c for c in containers
        if search.casefold() in c["name"].casefold()
    ]

    if not visible:
        st.info("No containers match your search")
    for container in visible:
        cid = container["id"]
        with st.container(border=True):
            left, right = st.columns([3, 2], vertical_alignment="center")
            left.subheader(container["name"])
            left.caption(cid[:12])
            with right:
                with st.container(horizontal=True):
                    state = container.get("state", "unknown")
                    st.badge(state, color="green" if state == "running" else "gray")
                    health = container.get("health", "unknown")
                    st.badge("Health: " + health, color="orange" if health == "unhealthy" else "gray")
            with st.container(horizontal=True):
                st.caption("Restarts: " + str(container.get("restart_count", "—")))
                st.caption("Collection: " + container.get("collection_status", "unknown"))
            if container.get("collection_status") != "ok":
                st.warning(container.get("collection_error") or "Some data could not be collected.")
                for warning in container.get("collection_warnings", []):
                    st.text(warning)
            findings = container.get("findings") or []
            with st.expander(f"Evidence and observations · {len(findings)} findings", icon=":material/manage_search:"):
                if not findings:
                    st.caption("No rule matched the recent sample. This does not guarantee that the application is healthy.")
                for finding in findings:
                    st.text(finding["category"])
                    st.code("\n".join(finding["evidence"]), language="text")
                with st.expander("Recent log sample"):
                    st.code("\n".join(container.get("log_sample") or []) or "No logs in this sample.", language="text")
            jobkey = f"analysis:{eid}:{cid}"
            if st.button("Analyze with AI", icon=":material/auto_awesome:", key=f"analyze:{eid}:{cid}",
                         disabled=not fresh or status not in ("ok", "partial") or container.get("collection_status") == "failed"):
                try:
                    st.session_state[jobkey] = api(f"/analysis?environment={eid}", {"container_id": cid})["job_id"]
                except RequestError as error:
                    handle_error(error)
            if st.session_state.get(jobkey):
                try:
                    with st.expander("Detailed analysis", expanded=True, icon=":material/auto_awesome:"):
                        show_analysis(api(f"/job?environment={eid}&id={st.session_state[jobkey]}"))
                except RequestError as error:
                    handle_error(error)

@st.fragment
def restart_sidebar():
    st.subheader("Auto-restart", icon=":material/restart_alt:")
    try:
        envs = api("/environments")["environments"]
        if not envs:
            st.info("No Docker environments available.")
            return
        envmap = {env["id"]: env["name"] for env in envs}
        eid = st.selectbox("Environment", list(envmap), format_func=envmap.get, key="restart_environment")
        cachekey = f"restart_settings:{eid}"
        reload_settings = st.button("Reload settings", key=f"reload_restart:{eid}")
        if cachekey not in st.session_state or reload_settings:
            st.session_state[cachekey] = api(f"/restart-settings?environment={eid}")["containers"]
            for item in st.session_state[cachekey]:
                st.session_state[f"restart_enabled:{eid}:{item['id']}"] = (
                    item.get("policy", {}).get("Name", "no") != "no")
        items = st.session_state[cachekey]
        st.caption("Checked: restart automatically. Manual stops are respected. Saving does not start stopped containers.")
        st.caption("Save uses unless-stopped for checked containers and no auto-restart for unchecked containers.")
        if not items:
            st.info("No containers in this environment.")
            return
        with st.form(f"restart_form:{eid}"):
            changes = []
            for item in items:
                unavailable = bool(item.get("error") or item.get("managed_by_swarm"))
                enabled = st.checkbox(item["name"], key=f"restart_enabled:{eid}:{item['id']}", disabled=unavailable)
                st.caption(item.get("error") or ("Managed by Swarm" if item.get("managed_by_swarm") else
                    f"{item['state']} · {item['policy']['Name']}"))
                if not unavailable:
                    changes.append({"id": item["id"], "enabled": enabled, "expected_policy": item["policy"]})
            submitted = st.form_submit_button("Save", type="primary", disabled=not changes, width="stretch")
        if submitted:
            result = api(f"/restart-settings?environment={eid}", {"changes": changes})
            byid = {item["id"]: item for item in items}
            failures = 0
            for saved in result["results"]:
                item = byid[saved["id"]]
                if saved["ok"]:
                    item["policy"] = saved["policy"]
                    for warning in saved.get("warnings", []):
                        st.warning(item["name"] + ": " + warning)
                else:
                    failures += 1
                    st.error(item["name"] + ": " + saved["message"])
            if not failures:
                st.success("Auto-restart settings saved.")
            else:
                st.warning("Some settings were not saved. Reload settings to check current values.")
    except RequestError as error:
        handle_error(error)


with st.sidebar:
    restart_sidebar()
workspace()

