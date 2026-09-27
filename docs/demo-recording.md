# Record the AI Monitor & Alerts demo

The dedicated `monitor-demo` container stays available after testing. It generates
no error automatically. It is separate from the monitoring and Portainer stacks,
and its HTTP endpoint is bound only to localhost on the VM.

## Prepare a clean take

From the VM terminal:

```bash
cd /srv/portainer-data/monitor-app
sudo docker compose -f compose.demo.yaml up -d --force-recreate --wait --wait-timeout 60
```

This recreates ONLY the demo container with a new container ID and empty logs. It
does not clear monitoring history or restart real applications. Use this before
rehearsing or recording again, because repeated alerts for the same container/rule
are intentionally suppressed for 15 minutes.

Open the monitoring dashboard, sign in with the Portainer admin account, choose the
VM's Docker environment and search for `monitor-demo`. Allow one collection cycle
(normally 30 seconds plus collection time) to see the new container without findings.
Open your private Telegram conversation with the alert bot.

## Record the demonstration

1. Show `monitor-demo` running with no current findings.
2. Run this in the VM terminal:

   ```bash
   curl -i http://127.0.0.1:18080/error
   ```

3. Show the real `HTTP/1.0 500 Internal Server Error` response. The container writes
   one access-log error. This is intentional and isolated to the demo application.
4. Return to the dashboard. After the next collection and UI refresh, expand its
   evidence to show the HTTP error rule and the matching log line.
5. Show the Telegram rule alert containing `monitor-demo`, HTTP error response,
   time and evidence. Delivery depends on network/API availability.
6. Explain: **the rule and Telegram alert did not require AI**. Optionally press
   **Analyze with AI** once to request a real explanation. A free-provider limit may
   prevent that optional step; display the actual result rather than a mock result.

The demo container remains running/healthy because one HTTP 500 response does not
prove the whole container is down. Its log remains in the five-minute monitoring
sample temporarily. Do not call the event an OOM, crash or outage.

## Expected timing and reset

Collection is configured every 30 seconds and the dashboard refreshes every 10
seconds. Slow/unreachable environments can extend this; these are not strict SLAs.
Telegram delivery is processed independently. Use the prepare command for another
take, then wait for the new container to appear before triggering `/error` again.

The demo is left installed for recording. If no longer needed, remove just this
optional stack with `sudo docker compose -f compose.demo.yaml down`.
