"""Persist lifecycle baselines; detect rapid restarts between collection samples."""
def observe(store, telegram, eid, environment, container, now):
    if container.get("collection_status") == "failed" or not container.get("state"):
        return
    key = f"lifecycle:{eid}:{container['id']}"
    previous = store.get(key)
    current = {k: container.get(k) for k in ("state", "restart_count", "started_at", "finished_at")}
    if previous:
        running = current["state"] == "running"
        was_running = previous["state"] == "running"
        automatic = (current.get("restart_count") or 0) > (previous.get("restart_count") or 0)
        new_start = bool(current.get("started_at") and previous.get("started_at")
                         and current["started_at"] != previous["started_at"])
        rapid = was_running and running and (automatic or new_start)
        stopped = (was_running and current["state"] in ("exited", "dead", "restarting")) or rapid
        returned = running and (previous["state"] in ("exited", "dead", "restarting") or rapid)
        for event, title in (("stopped", "Container stopped"), ("returned", "Container restarted")):
            if not (stopped if event == "stopped" else returned):
                continue
            evidence = ("Restart detected between monitoring samples." if rapid else
                        f"State changed from {previous['state']} to {current['state']}.")
            if event == "returned" and automatic:
                evidence += " Docker automatic restart count increased."
            identity = [event, previous, current]
            finding = {"source": "rules", "rule": "container_" + event,
                       "category": title, "facts": {"transition": identity}, "evidence": [evidence]}
            store.notice(eid, container["id"], "lifecycle", title,
                         {"container_name": container["name"], **finding}, identity)
            telegram.observe(eid, environment, container, finding, now)
    store.put(key, current)
