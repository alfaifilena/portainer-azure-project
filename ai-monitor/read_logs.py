import json
import ssl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from check_connection import PORTAINER_URL, TOKEN_FILE, CERT_FILE
from read_containers import ENVIRONMENT_ID

CONTAINER_NAME = "container-hub-demo-demo-web-1"


def decode_logs(data, tty):
    if tty:
        return data.decode("utf-8", errors="replace")

    # Docker separates stdout and stderr using 8-byte frame headers.
    chunks = []
    position = 0

    while position < len(data):
        header = data[position:position + 8]

        if len(header) != 8:
            raise ValueError("Incomplete Docker log header.")

        if header[0] not in (0, 1, 2) or header[1:4] != b"\x00\x00\x00":
            raise ValueError("Unexpected Docker log format.")

        size = int.from_bytes(header[4:8], byteorder="big")
        start = position + 8
        end = start + size

        if end > len(data):
            raise ValueError("Incomplete Docker log message.")

        chunks.append(data[start:end])
        position = end

    return b"".join(chunks).decode("utf-8", errors="replace")


def main():
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    if not token:
        raise ValueError("The token file is empty.")

    tls_context = ssl.create_default_context(cafile=str(CERT_FILE))
    base_url = (
        f"{PORTAINER_URL}/api/endpoints/{ENVIRONMENT_ID}"
        f"/docker/containers/{CONTAINER_NAME}"
    )

    def get(path):
        request = Request(
            base_url + path,
            headers={"X-API-Key": token},
            method="GET",
        )
        with urlopen(request, context=tls_context, timeout=10) as response:
            return response.read()

    details = json.loads(get("/json"))

    raw_logs = get(
        "/logs?stdout=true&stderr=true&timestamps=true&tail=30"
    )

    logs = decode_logs(raw_logs, details["Config"].get("Tty", False))

    print(f"Container: {CONTAINER_NAME}")
    print("--- Recent logs ---")
    print(logs if logs.strip() else "No logs returned.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"HTTP error: {error.code}")
        raise SystemExit(1)
    except (URLError, OSError, ValueError) as error:
        print(f"Log query failed: {error}")
        raise SystemExit(1)
