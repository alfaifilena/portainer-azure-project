# Container Hub monitoring

Rules collect Docker observations every 30 seconds, independently of admin sessions.
They classify evidence in a bounded five-minute log sample and Docker state: HTTP
4xx/5xx, connection/runtime errors, unhealthy/restarting state, recent OOM and error
exits. A match is an observation, not proof of a root cause or complete coverage.
Missing healthchecks and clean exits are not errors; exit 137 alone is not proof of OOM.

## AI only on request

Only `POST /analysis`, issued by **Analyze with AI**, starts a provider request.
Opening/refreshing the dashboard, collection and Telegram never call AI.
Automatic AI detection, its interval setting and the AI queue worker are removed.
Only one analysis runs at a time. Busy requests return 409; cooldown or budget
rejections return 429. Rejected requests are not saved for later and do not consume
request budgets. Accepted analyses appear as running and are polled through `/job`.

The server revalidates the admin role, container access and freshness before sending
data. Sessions expire after 45 seconds without a successful workspace refresh and
at most one hour after sign-in. Signing out prevents requests that have not started;
an already dispatched provider request may complete. Passwords and JWTs are not stored
in SQLite or forwarded to AI. The opaque job owner ID is stripped before dispatch.

OpenRouter receives bounded redacted observations only, using `openrouter/free` with
no paid fallback. Results are advisory and never execute actions. The configured
budgets count accepted analysis attempts: 300/day globally in this deployment and
10/day/user, resetting at 00:00 UTC. These are independent of OpenRouter's limits.
Rate/auth/credit failures set a five-minute cooldown (longer Retry-After is respected),
other failures one minute. Cooldown persists across restarts; users must click again
after it ends. Free-provider success during a demo is not guaranteed.

## Telegram rule alerts

A dedicated bot sends only current rule findings to one configured private chat,
including HTTP 4xx and 5xx. No AI guesses, normal-status, recovery or routine heartbeat
messages are sent. Collection and alerts continue after admin logout.

Alerts contain environment/container names, rule category, observation time and one
redacted evidence line (maximum 400 characters). Redaction is best-effort. Full logs,
Docker environment variables and tokens are never sent. Identical environment,
container, rule and facts are suppressed for 15 minutes, persisted in SQLite. A new
observation after that interval can alert again; old notification history is not replayed.

Delivery is separate from collection, with a 10-second network timeout and at most
three attempts per alert. Transient retries back off from 30 seconds and honor Telegram
retry_after; pending alerts expire after 15 minutes. Invalid credentials/destination
pause delivery until credentials change. Delivery errors are visible on the dashboard.
An ambiguous network failure can result in a duplicate; exactly-once delivery is not guaranteed.

Create a new bot using Telegram's BotFather, then run on the VM:

```bash
sudo python3 /srv/portainer-data/monitor-app/scripts/setup_telegram.py
```

Enter the bot token at the hidden prompt, open the generated private Start link,
press Start, then press Enter in the terminal. The script saves root-only files at
`/srv/portainer-data/config/secrets/telegram_bot_token` and `telegram_chat_id`.
Never commit these files or paste tokens into chat. The monitor rereads the files;
changing existing file contents does not require rebuilding the image.

## Deployment and verification

The monitoring stack remains separate from Portainer. Source lives at
`/srv/portainer-data/monitor-app`; SQLite lives on the data disk. Back up source and
use SQLite's online backup API before upgrades. The migration adds Telegram delivery
state and interrupts legacy queued/running AI jobs without deleting reports or usage.
Historical AI detections remain in the database but are hidden from current reports.

Before the first deployment, create empty Telegram secret files if setup has not yet
been run, with root ownership and mode 600. Bind only the named files, not the secret
directory. Until configured, Telegram displays `not configured` and rules still work.

```bash
python3 -m unittest discover -s ai-monitor/tests -v
# Requires dashboard/requirements.txt in the test environment:
python3 -m unittest discover -s dashboard/tests -v
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml config --quiet
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml build
sudo docker compose -f compose.monitor.yaml -f compose.dashboard.yaml up -d --wait --wait-timeout 120
```

No public API port is added. Dashboard remains behind the existing `/ai/` HTTPS route.
Verify admin sign-in/out, no AI requests during refresh/collection, immediate running
or rejection on button press, and a rule alert from a disposable test container.
Verify repeated samples do not resend the same alert. Live AI testing is a user click;
offline tests mock providers and Telegram.

To disable AI for rule-only validation, include `compose.validation.yaml` when starting
the stack. Telegram still operates if configured. To roll back, restore the backed-up
source and rebuild the monitoring stack; added SQLite tables can remain in place.
