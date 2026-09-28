"""Evidence-based classification, without severity or priority scores."""
import re
from datetime import datetime

CATALOG = {
    "connection_refused": "Connection refused",
    "timeout": "Connection or operation timed out",
    "dns_failure": "Name resolution failed",
    "connection_interrupted": "Connection interrupted",
    "address_in_use": "Address already in use",
    "permission_denied": "Permission denied",
    "file_missing": "File or path missing",
    "read_only_filesystem": "Read-only filesystem",
    "storage_exhausted": "Storage allocation failed",
    "application_memory": "Application memory exhausted",
    "authentication_failed": "Authentication failed",
    "tls_error": "TLS or certificate error",
    "configuration_error": "Missing or invalid configuration",
    "dependency_missing": "Dependency or command missing",
    "http_error": "HTTP error response",
    "application_exception": "Application exception",
}
STATE_CATALOG = {
    "container_unhealthy": "Healthcheck failing",
    "container_restarting": "Container restarting",
    "container_oom_killed": "Recent OOM kill reported by Docker",
    "container_exit_error": "Container termination error",
}
SIGNATURES = {key: re.compile(pattern, re.I) for key, pattern in {
    "connection_refused": r"\b(?:ECONNREFUSED|ConnectionRefusedError)\b|connection refused",
    "timeout": r"\b(?:ETIMEDOUT|ReadTimeout|ConnectTimeout|TimeoutError)\b|(?:connection|read|request|operation) timed out",
    "dns_failure": r"\b(?:EAI_AGAIN|EAI_NONAME|ENOTFOUND)\b|socket\.gaierror|host not found in upstream|could not resolve host|temporary failure in name resolution|name or service not known",
    "connection_interrupted": r"\b(?:ECONNRESET|EPIPE)\b|connection reset by peer|broken pipe",
    "address_in_use": r"\bEADDRINUSE\b|address already in use",
    "permission_denied": r"\b(?:EACCES|EPERM|PermissionError)\b|permission denied|operation not permitted",
    "file_missing": r"\b(?:ENOENT|FileNotFoundError)\b|no such file or directory",
    "read_only_filesystem": r"\bEROFS\b|read-only file system",
    "storage_exhausted": r"\b(?:ENOSPC|EDQUOT)\b|no space left on device|disk quota exceeded",
    "application_memory": r"\b(?:OutOfMemoryError|MemoryError)\b|heap out of memory|cannot allocate memory",
    "authentication_failed": r"password authentication failed|invalid credentials|authentication (?:failed|failure)|access denied for user",
    "tls_error": r"certificate verify failed|certificate has expired|TLS handshake (?:failed|error)|SSL handshake (?:failed|error)|SSLCertVerificationError",
    "configuration_error": r"(?:missing|required|invalid) (?:environment variable|configuration|config value)|(?:environment variable|configuration (?:key|value)) .{0,100}(?:not set|missing|invalid|required)",
    "dependency_missing": r"ModuleNotFoundError|cannot find module|command not found|ImportError: (?:No module named|cannot import name)",
}.items()}
ACCESS = re.compile(r'"[A-Z]+ [^"\r\n]+ HTTP/\d(?:\.\d)?"\s+(\d{3})\b')
EXCEPTION = re.compile(r"\b(?:[\w.]+Error|[\w.]+Exception):\s*\S|panic:\s*\S|segmentation fault", re.I)

def redact(value):
    """Best effort; bounded samples only, never Docker environment variables."""
    text = str(value)
    text = re.sub(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+\S+", r"\1 [REDACTED]", text)
    text = re.sub(r'''(?i)(["']?(?:password|passwd|token|access_token|api[_-]?key|secret|authorization|cookie)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''', r"\1[REDACTED]", text)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b(?:sk-or-v1-|sk-)[A-Za-z0-9_-]{10,}\b", "[REDACTED]", text)
    text = re.sub(r"\?[^\s\"']+", "?[REDACTED]", text)
    return text[:64000]

def epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo and parsed.year >= 1970 else None
    except (ValueError, TypeError, AttributeError):
        return None

def finding(rule, evidence, facts=None):
    return {"rule": rule, "category": (CATALOG | STATE_CATALOG)[rule],
            "source": "rules", "evidence": [redact(x)[:1200] for x in evidence[-5:]],
            "confirmed_evidence": (CATALOG | STATE_CATALOG)[rule] + " observed in the supplied sample.",
            "occurrences": len(evidence), "facts": facts or {}}

def log_records(logs, since, now):
    records = []
    for line in redact(logs).splitlines():
        timestamp = epoch(line.partition(" ")[0])
        if timestamp is not None and since <= timestamp <= now + 5:
            records.append(line[:1200])
    return records

def detect(details, logs, since, now):
    results, matches = [], {}
    state = details["State"]
    status = state["Status"]
    if status == "running" and state.get("Health", {}).get("Status") == "unhealthy":
        results.append(finding("container_unhealthy", ["Docker Health.Status=unhealthy"]))
    if status == "restarting":
        results.append(finding("container_restarting", ["Docker State.Status=restarting; a restart loop is not proven."]))
    finished = epoch(state.get("FinishedAt"))
    recent = finished is not None and since <= finished <= now + 5
    if recent and state.get("OOMKilled") is True:
        results.append(finding("container_oom_killed", ["Docker OOMKilled=true at " + state["FinishedAt"]]))
    elif status == "dead" or (status == "exited" and recent and state.get("ExitCode", 0) != 0):
        results.append(finding("container_exit_error", [f"Docker state={status}, exit={state.get('ExitCode')}"]))
    for line in log_records(logs or "", since, now):
        access = ACCESS.search(line)
        if access:
            code = int(access[1])
            if 400 <= code <= 599:
                matches.setdefault(("http_error", code), []).append(line)
            continue
        keys = [key for key, pattern in SIGNATURES.items() if pattern.search(line)]
        if "dependency_missing" in keys and "file_missing" in keys:
            keys.remove("file_missing")
        if not keys and EXCEPTION.search(line):
            keys = ["application_exception"]
        for key in keys:
            matches.setdefault((key, None), []).append(line)
    for (key, code), evidence in matches.items():
        results.append(finding(key, evidence, {"http_status": code} if code else {}))
    return results

