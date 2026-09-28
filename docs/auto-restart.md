# Keep-running selection and lifecycle notifications

In the sidebar, choose an Environment, select containers, and press Save.
Checked containers are kept running, even after manual Stop. Selected stopped
containers are started on the next monitoring cycle (normally about 30 seconds,
longer with slow or unavailable environments). Uncheck and Save BEFORE stopping
a container that should remain off. Save never stops a running container.

After upgrading, press Save once to persist your keep-running selection.
Existing native policies alone do not authorize the monitor to start containers.
Selections persist across monitor restarts and are tied to exact container IDs.
Reselect replacements after a container recreation or stack redeployment.

Checked containers also use Docker `unless-stopped`; unchecked containers use `no`.
The list initially reflects the current Docker policy. Save normalizes checked
policies (including `always` and `on-failure`) to `unless-stopped`.
Reload settings to discard edits and read current settings. Each failed update
is shown separately; successful updates remain applied.

The reconciler starts only explicitly selected containers in exited/created state,
with a 30-second retry backoff. Paused/dead containers and containers whose native
policy was disabled outside the app are left alone. Failed starts produce a
dashboard notice. Recovery is reported only after inspect confirms running.
Swarm tasks must be configured on their service and cannot be edited here.
Compose/Stack redeployment can replace runtime settings: set the same `restart`
policy in that deployment's source for persistence across container recreation.

The monitor records a baseline without alerting on existing stopped containers.
Subsequent observed stops and returns create dashboard and Telegram notices.
Changed start timestamps and increasing restart counts also detect rapid
restarts between polling samples. These are reported as observed restarts;
the monitor does not infer a crash cause or exact event time. Multiple restarts
between samples are summarized. Monitoring outages can miss intermediate events.
Persistent baselines prevent duplicate notices on unchanged samples or monitor
restarts. Telegram uses the existing retry and expiration rules.

Settings updates use the signed-in administrator's Portainer credentials.
Recovery uses the monitoring service token to inspect/start persisted selections,
and requires start permission. Save and recovery share a lock so disabling
cannot race a new start. Access and current policy are rechecked when saving. The app
cannot atomically compare-and-update Docker policy against outside writers.

This is recovery on one Docker host, not host failover. An unhealthy container
whose main process still runs is not restarted by a Docker restart policy.
The monitor must be running to recover a manual Stop; it cannot restart itself
after it is manually stopped.
