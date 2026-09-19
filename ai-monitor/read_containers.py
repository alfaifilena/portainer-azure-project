import json
import ssl
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from check_connection import PORTAINER_URL, TOKEN_FILE, CERT_FILE

ENVIRONMENT_ID = 3


def main():
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    if not token:
        raise ValueError("The token file is empty.")

    tls_context = ssl.create_default_context(cafile=str(CERT_FILE))

    # Select only the demo service in our Compose project.
    filters = {
        "label": [
            "com.docker.compose.project=container-hub-demo",
            "com.docker.compose.service=demo-web",
        ]
    }

    query = urlencode({
        "all": "true",
        "filters": json.dumps(filters),
    })

    url = (
        f"{PORTAINER_URL}/api/endpoints/{ENVIRONMENT_ID}"
        f"/docker/containers/json?{query}"
    )

    request = Request(
        url,
        headers={"X-API-Key": token, "Accept": "application/json"},
        method="GET",
    )

    with urlopen(request, context=tls_context, timeout=10) as response:
        containers = json.load(response)

    if not containers:
        print("No matching demo container found.")
        print("Check the deployment and Compose project name.")
        return

    for container in containers:
        names = container.get("Names") or [container["Id"][:12]]
        name = names[0].lstrip("/") 
        details_url = (
            f"{PORTAINER_URL}/api/endpoints/{ENVIRONMENT_ID}"
            f"/docker/containers/{container['Id']}/json"
        )

        details_request = Request(
            details_url,
            headers={"X-API-Key": token, "Accept": "application/json"},
            method="GET",
        )

        with urlopen(
            details_request, context=tls_context, timeout=10
        ) as response:
            details = json.load(response)

        state = details["State"]
        health = state.get("Health", {}).get("Status", "not configured")

        print(f"Container: {name}")
        print(f"State: {state['Status']}")
        print(f"Health: {health}")
        print(f"Restart count: {details.get('RestartCount', 0)}")
        print(f"OOM killed: {state.get('OOMKilled', False)}")

        if state["Status"] in ("exited", "dead"):
            print(f"Exit code: {state.get('ExitCode')}")

        print()


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"HTTP error: {error.code}")
        print("Check the environment ID, token, and permissions.")
        raise SystemExit(1)
    except (URLError, OSError, ValueError) as error:
        print(f"Container query failed: {error}")
        raise SystemExit(1)
