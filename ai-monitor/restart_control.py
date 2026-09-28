"""User-authorized restart settings; never start or stop a container."""
from urllib.error import HTTPError


def settings(client, eid, cid, jwt):
    item = client.restart_settings(eid, cid, jwt=jwt)
    return {"id": cid, **item}


def save(client, eid, changes, allowed, jwt):
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
            results.append({"id": cid, "ok": True, "policy": policy, "warnings": warnings})
        except HTTPError as error:
            results.append({"id": cid, "ok": False, "message":
                "Portainer denied this update." if error.code in (401, 403) else "Container update failed. Reload settings."})
        except ValueError as error:
            results.append({"id": cid, "ok": False, "message": str(error)})
        except OSError:
            results.append({"id": cid, "ok": False, "message": "Connection failed. Reload settings to check the result."})
    return {"results": results}
