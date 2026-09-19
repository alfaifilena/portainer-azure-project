import json
import os
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import streamlit as st

REPORT_URL = os.environ.get(
    "REPORT_URL", "http://ai-monitor:8090/report"
)

st.set_page_config(
    page_title="Container AI Monitor",
    page_icon="🔎",
    layout="wide",
)

st.title("Container AI Monitor")
st.caption("Container status, detected issues, and evidence-based AI analysis.")


@st.fragment(run_every=10)
def display_report():
    try:
        with urlopen(REPORT_URL, timeout=5) as response:
            report = json.load(response)

        checked = datetime.fromisoformat(report["checked_at"])
        age = (datetime.now(timezone.utc) - checked).total_seconds()

        if not isinstance(report.get("containers", []), list):
            raise ValueError("Invalid container list.")

    except HTTPError as error:
        if error.code == 503:
            st.info("Monitoring is starting. Waiting for the first report.")
        else:
            st.error(f"Report service returned HTTP {error.code}.")
        return
    except (URLError, OSError, ValueError, KeyError, TypeError):
        st.error("Monitoring data is unavailable. Container health is unknown.")
        return

    st.caption(f"Last collection: {checked.isoformat()}")

    if age > 150:
        st.warning(
            "This report is more than 150 seconds old. "
            "The values below may not reflect the current state."
        )
    elif age < -10:
        st.warning("The report clock is ahead. Check the server time.")

    status = report.get("collection_status")

    if status not in ("ok", "partial"):
        st.error("The latest collection failed. Container health is unknown.")
        st.text(report.get("collection_error", "No details available."))
        return

    if status == "partial":
        st.warning("Some container data could not be collected.")

    containers = report["containers"]
    findings_count = sum(
        len(container.get("findings") or [])
        for container in containers
    )

    first, second, third = st.columns(3)
    first.metric("Selected containers", len(containers))
    second.metric("Rule matches in this report", findings_count)
    third.metric(
        "AI requests since monitor start",
        report.get("ai_requests_used_this_run", "Unknown"),
    )

    rules = ", ".join(report.get("rule_coverage", []))
    st.caption(f"Detection coverage: {rules or 'Not reported'}")
    st.caption(
        "No matches means no supported rule matched the sampled logs. "
        "It does not prove that every service is healthy."
    )

    if not containers:
        st.info("No containers matched the current monitoring filter.")
        return

    for container in containers:
        with st.container(border=True):
            st.subheader(container["name"])

            st.text(
                f"State: {container.get('state', 'unknown')}  |  "
                f"Health: {container.get('health', 'unknown')}  |  "
                f"Restart count: {container.get('restart_count', 'unknown')}"
            )

            if container.get("collection_status") != "ok":
                st.error("Collection failed for this container.")
                st.text(container.get("collection_error", "Unknown error"))
                continue

            st.text(
                f"OOM killed: {container.get('oom_killed')}  |  "
                f"Exit code: {container.get('exit_code')}"
            )

            findings = container.get("findings") or []

            if not findings:
                st.info("No supported rule matched the recent log sample.")

            for finding in findings:
                st.markdown("**Detected issue**")
                st.text(
                    f"{finding['category']} | "
                    f"Rule severity: {finding['severity']}"
                )
                st.text(finding["confirmed_evidence"])

                with st.expander("View log evidence"):
                    st.code(
                        "\n".join(finding.get("evidence", [])),
                        language="text",
                    )

                ai = finding.get("ai") or {}
                if ai.get("status") != "ready":
                    st.caption(
                        f"AI analysis: {ai.get('status', 'not available')}"
                    )
                    if ai.get("error"):
                        st.text(ai["error"])
                    continue

                analysis = ai["ai_analysis"]
                st.markdown("**AI analysis**")
                st.caption(
                    f"Source: {ai.get('source')} | "
                    f"Created: {ai.get('analysis_created_at')} | "
                    f"Model: {ai.get('model_used')}"
                )

                fields = [
                    ("Error type", "error_type"),
                    ("AI severity", "severity"),
                    ("Confirmed evidence", "confirmed_evidence"),
                    ("Possible cause — not confirmed", "possible_cause"),
                    ("Suggested checks", "suggested_solution"),
                    ("Uncertainty", "uncertainty"),
                ]

                for label, key in fields:
                    st.markdown(f"**{label}**")
                    st.text(analysis.get(key, "Not provided"))

                if analysis.get("severity") != finding["severity"]:
                    st.warning("AI severity differs from the rule severity.")

                st.caption("Analysis only. No remediation action was executed.")


display_report()
