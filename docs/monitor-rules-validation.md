# Container Hub monitor

The deployed monitor stack is independent of the existing Portainer stack.
Do not merge the monitor Compose files into the original Portainer deployment.

## Paths and operations

- Source on VM: /srv/portainer-data/monitor-app
- SQLite data, notifications, reads, AI jobs and daily usage: /srv/portainer-data/ai-monitor/monitor.sqlite3
- Credentials and trusted Portainer certificate: /srv/portainer-data/config/secrets
- Public dashboard: https://portainer-container-hub.eastus.cloudapp.azure.com/ai/
- Internal API: ai-monitor:8090, not published to the host
- Dashboard listener: 127.0.0.1:8501, reached through Nginx HTTPS

Run from /srv/portainer-data/monitor-app:

```bash
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml ps
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml logs --tail 50
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml up -d --build --wait
```

Use a Portainer username/password to sign in; VM Entra ID authentication is separate.
User JWTs and dashboard session tokens exist only in memory, expire after at most one hour,
and are removed at logout. Passwords are forwarded to Portainer only and never persisted.
Every data request verifies the user and role, lists accessible environments and containers
using that user's JWT, and filters reports, notifications and jobs. User requests never
fall back to the monitor service token. Access checks fail closed when Portainer is unavailable.
The API is private to Docker networks; do not publish port 8090.

## Collection and AI

The service token collects supported Docker environments (types 1, 2, 4), independently
of signed-in users. environment_ids=[] selects all supported environments visible to
the monitor token. container_filters={} selects all accessible containers, including stopped.
Set these filters in ai-monitor/config.docker.json to narrow monitoring.

Collection runs every 30 seconds, sampling up to 100 recent lines per container within
a five-minute window. Rules detect runtime signatures, HTTP errors and Docker state.
No severity or priority is assigned. A missing healthcheck is not an error; a clean stop
is not an outage; exit 137 alone does not prove OOM. Partial log failures preserve state findings.
No rule match is not proof of health. UI marks reports older than 150 seconds as stale.

AI detection queues newly seen redacted lines at most once per minute per container.
It can identify unfamiliar errors. The response must quote exact supplied evidence;
AI classifications remain advisory. Detailed analysis is requested by clicking Analyze with AI.
No container changes or remediation commands are executed.

OpenRouter receives bounded redacted log samples, container names/IDs, state and findings.
Redaction is best-effort and does not guarantee removal of all application-specific secrets.
Docker environment variables and configuration are not sent.
The configured model is openrouter/free; there is no paid-model fallback.
Default limits: 100 provider attempts/day total and 10 analysis submissions/day/user,
reset at 00:00 UTC, persisted across restarts. Cached identical analyses last 15 minutes.
Provider failure/invalid output is shown as unavailable. Auth/credit/rate-limit errors
pause the worker for five minutes, other errors for one minute. Restart interrupts running
jobs; queued jobs resume. Free-provider availability is not guaranteed.

Notifications persist for 30 days. Identical rule/category/facts share one notification;
new evidence updates it and makes it unread again. Read state is per user.
AI observations are deduplicated by evidence. This is an observation inbox, not incident
resolution tracking. Removed or newly inaccessible containers are hidden.
Only the most recent 500 stored notifications in an environment are considered per request.

## Tests

```bash
python -m unittest discover -s ai-monitor/tests -v
python -m unittest discover -s dashboard/tests -v
```

Tests cover timestamp filtering, HTTP context, Docker framing, partial collection,
redaction, scope isolation, revocation, notification persistence, AI evidence validation,
queue deduplication, budgets and dashboard interactions. They use synthetic fixtures.

To disable AI calls during rule validation:

```bash
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml -f compose.validation.yaml up -d
```

Restore the normal configuration by omitting compose.validation.yaml.

## Backups and rollback

The deployment script saves Nginx configuration before adding /ai/, validates nginx -t
before reloading, and restores that configuration if validation or reload fails.
Nginx backups are in /srv/portainer-data/config/backups.

Back up monitor-app, config/secrets, Nginx configuration, TLS certificates, and an online
SQLite backup together. Do not copy only the SQLite file while WAL writes are active;
use sqlite3.Connection.backup(), or stop ai-monitor while taking a consistent backup.
Keeping data on a separate disk is not itself a backup.

To stop this feature without stopping Portainer:

```bash
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml stop
```

Then remove only the marked Container Hub AI dashboard locations from Nginx, run nginx -t,
and reload Nginx. Keep the database and credentials for recovery.

## References

- https://docs.portainer.io/api/access
- https://openrouter.ai/docs/guides/features/structured-outputs

