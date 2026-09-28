# Auto-restart and lifecycle notifications

In the sidebar, choose an Environment, select containers, and press Save.
Checked containers use Docker `unless-stopped`; unchecked containers use `no`.
The list initially reflects the current Docker policy. Save normalizes checked
policies (including `always` and `on-failure`) to `unless-stopped`.
Reload settings to discard edits and read current settings. Each failed update
is shown separately; successful updates remain applied.

Saving never starts or stops containers. Initially stopped containers stay
stopped. Manual stops are respected, including across Docker daemon restarts.
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

Updates use the signed-in user's Portainer credentials, never the monitoring
service token. Access and current policy are rechecked when saving. The app
cannot atomically compare-and-update Docker policy against outside writers.

This is recovery on one Docker host, not host failover. An unhealthy container
whose main process still runs is not restarted by a Docker restart policy.
