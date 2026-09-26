"""Server-side Portainer client. User reads NEVER fall back to service credentials."""
import base64
import json
import ssl
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE = 4 * 1024 * 1024

class Portainer:
    def __init__(self, config):
        self.config = config
        self.base = config["portainer_url"].rstrip("/")
        parsed = urlsplit(self.base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Portainer must use HTTPS without embedded credentials.")
        ca = config.get("certificate_file")
        self.tls = ssl.create_default_context(cafile=ca or None)

    def request(self, path, *, jwt=None, service=False, body=None):
        if not path.startswith("/api/") or ".." in path:
            raise ValueError("Invalid Portainer API path.")
        headers = {"Accept": "application/json"}
        if jwt:
            headers["Authorization"] = "Bearer " + jwt
        elif service:
            headers["X-API-Key"] = Path(self.config["token_file"]).read_text().strip()
        elif path != "/api/auth":
            raise ValueError("Authentication required.")
        data = None
        if body is not None:
            if path != "/api/auth":
                raise ValueError("Only authentication may use POST.")
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        with urlopen(Request(self.base + path, headers=headers, data=data),
                     context=self.tls, timeout=15) as response:
            result = response.read(MAX_RESPONSE + 1)
        if len(result) > MAX_RESPONSE:
            raise ValueError("Portainer response exceeded sample limit.")
        return result

    def json(self, path, **kwargs):
        return json.loads(self.request(path, **kwargs))

    def login(self, username, password):
        result = self.json("/api/auth", body={"Username": username, "Password": password})
        jwt = result["jwt"]
        # Claims locate the user only. Portainer verifies the JWT on the next call.
        part = jwt.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        uid = int(claims["id"])
        user = self.json(f"/api/users/{uid}", jwt=jwt)
        if user["Id"] != uid:
            raise ValueError("Identity mismatch.")
        return jwt, user, float(claims["exp"])

    def environments(self, **kwargs):
        result = self.json("/api/endpoints?limit=0", **kwargs)
        if not isinstance(result, list):
            raise ValueError("Invalid environment response.")
        allowed = self.config.get("environment_ids") or []
        # Kubernetes and Edge async modes need a different collector.
        return [x for x in result if x.get("Type") in (1, 2, 4)
                and (not allowed or x["Id"] in allowed)]

    def containers(self, environment, **kwargs):
        result = self.json(f"/api/endpoints/{environment}/docker/containers/json?all=1", **kwargs)
        if not isinstance(result, list):
            raise ValueError("Invalid container response.")
        return result

