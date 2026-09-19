import json
import ssl
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Locate the project regardless of the terminal's current folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

PORTAINER_URL = "https://localhost:9443"
TOKEN_FILE = PROJECT_ROOT / "secrets" / "portainer_api_token"
CERT_FILE = PROJECT_ROOT / "secrets" / "portainer.crt"


def main():
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    if not token:
        raise ValueError("The token file is empty.")

    tls_context = ssl.create_default_context(cafile=str(CERT_FILE))

    request = Request(
        f"{PORTAINER_URL}/api/endpoints",
        headers={
            "X-API-Key": token,
            "Accept": "application/json",
        },
        method="GET",
    )

    with urlopen(request, context=tls_context, timeout=10) as response:
        environments = json.load(response)

    print("Authenticated connection succeeded.")

    if not environments:
        print("No environments are available to this account.")
        return

    for environment in environments:
        print(
            f"Environment ID: {environment['Id']} | "
            f"Name: {environment['Name']}"
        )


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"HTTP error: {error.code}")
        print("Check the token and account permissions.")
        raise SystemExit(1)
    except (URLError, OSError, ValueError) as error:
        print(f"Connection check failed: {error}")
        raise SystemExit(1)
