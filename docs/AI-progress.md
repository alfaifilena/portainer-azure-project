# AI monitoring progress

## Verified locally
- Portainer API authentication and TLS verification.
- Container state, health, restart count and OOM flag collection.
- Reading recent container logs.
- HTTP 404 detection from real Nginx requests.
- OpenRouter free-model analysis with structured output validation.
- Monitoring and AI analysis running inside Docker.
- In-memory analysis reuse and retry cooldown.
- Internal report API.
- Streamlit dashboard displaying reports and AI analysis.

## Current limits
- Monitoring is filtered to the local demo Compose project.
- The only implemented detection rule is nginx_http_404.
- AI receives normalized observations, not raw logs.
- Analysis memory and request counters reset on monitor restart.
- There is no database or persistent incident history.
- Alerts and remediation are not implemented.
- Deployment to the team VM has not been tested.

## Configuration
The JSON configuration files contain local environment settings.
Change the Portainer URL, environment ID, certificate and token file
configuration when deploying to another environment.

Real tokens, private keys and .env must not be committed.

## Next work
Expand and test detection rules, then prepare deployment to the team VM.
