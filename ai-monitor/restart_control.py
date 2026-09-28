"""Persist explicit keep-running choices and recover selected containers."""
import time
from urllib.error import HTTPError


def settings(client, eid, cid, jwt):
    item = client.restart_settings(eid, cid, jwt=jwt)
    return {"id": cid, **item}


def save(client, eid, changes, allowed, jwt, store=None):
    if not isinstance(changes, list) or len(changes) > 500:
        raise ValueError("Invalid container selection.")
    seen = set()
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("Invalid container selection.")
        cid = change.get("id")
        if not isinstance(cid, str) or cid not in allowed or cid in seen:
            raise ValueError("Container access changed. Reload the list.")
        seen.add(cid)
        if type(change.get("enabled")) is not bool:
            raise ValueError("Invalid auto-restart selection.")
        client.validate_restart_policy(change.get("expected_policy"))
    results = []
    for change in changes:
        cid = change["id"]
        try:
            current = settings(client, eid, cid, jwt)
            if current["managed_by_swarm"]:
                raise ValueError("Manage this container through its Swarm service.")
            if current["policy"] != change["expected_policy"]:
                raise ValueError("Settings changed. Reload the list before saving.")
            policy = {"Name": "unless-stopped" if change["enabled"] else "no", "MaximumRetryCount": 0}
            warnings = []
            if policy != current["policy"]:
                response = client.update_restart_policy(eid, cid, policy, jwt=jwt)
                warnings = response.get("Warnings") or []
            actual = settings(client, eid, cid, jwt)
            if actual["policy"] != policy:
                raise ValueError("Policy could not be verified. Reload settings.")
            if store is not None:
                store.put(f"keep_running:{eid}:{cid}", {"enabled": change["enabled"], "retry_at": 0})
            results.append({"id": cid, "ok": True, "policy": policy, "warnings": warnings})
        except HTTPError as error:
            results.append({"id": cid, "ok": False, "message":
                "Portainer denied this update." if error.code in (401, 403) else "Container update failed. Reload settings."})
        except ValueError as error:
            results.append({"id": cid, "ok": False, "message": str(error)})
        except OSError:
            results.append({"id": cid, "ok": False, "message": "Connection failed. Reload settings to check the result."})
    return {"results": results}


def recover(client, store, eid, container, now):
    """Caller holds the same lock as Save; disabling cannot race a start."""
    key = f"keep_running:{eid}:{container['id']}"
    choice = store.get(key, {})
    if not choice.get("enabled") or now < choice.get("retry_at", 0):
        return False
    if container.get("state") not in ("exited", "created"):
        return False
    try:
        live = client.restart_settings(eid, container["id"], service=True)
        if live["managed_by_swarm"] or live["policy"]["Name"] == "no":
            return False
        if live["state"] not in ("exited", "created"):
            return False
        # One start per container per 30 seconds even if the application exits immediately.
        store.put(key, {**choice, "retry_at": time.time() + 30})
        try:
            client.start_container(eid, container["id"])
        except HTTPError as error:
            if error.code != 304:  # Docker reports already-running if another actor won the race.
                raise
        live = client.restart_settings(eid, container["id"], service=True)
        if live["state"] != "running":
            raise ValueError("Container did not stay running.")
        container.update({k: live[k] for k in ("state", "restart_count", "started_at", "finished_at")})
        container["health"] = "awaiting next collection"
        container["exit_code"] = None
        store.put(key, {**choice, "retry_at": time.time() + 30, "last_started": now})
        return True
    except (OSError, ValueError, KeyError):
        store.put(key, {**choice, "retry_at": time.time() + 30, "error": "Automatic start failed."})
        store.notice(eid, container["id"], "lifecycle", "Automatic restart failed",
            {"container_name": container["name"], "evidence": [
                "Check Portainer start permissions and container configuration. Retrying on the next monitoring cycle."]},
            ["auto_start_failed", container.get("finished_at")])
        return False
