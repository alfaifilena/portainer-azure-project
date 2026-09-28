## Environment
Tested on Ubuntu 24.04 in WSL2 with Docker Desktop integration.

## Requirements
- Docker Desktop running with integration enabled for Ubuntu.
- Docker Compose available through `docker compose`.
- Bash, OpenSSL and curl.

## First run
From the repository root:

```bash
bash scripts/init.sh
bash scripts/deploy.sh
```

Initialization creates `.env` from `.env.example` and generates
a local TLS certificate and private key under `secrets/`.

These generated files must not be committed to Git.

## Access
- Portainer: https://localhost:9443
- Demo: http://localhost:8081

On a fresh installation, create a Portainer administrator account.
For an existing installation, use the existing account.

A browser warning is expected for the locally generated,
self-signed certificate.

The services are published on the local machine only.
Portainer can show other containers on the same Docker engine.

## Verify HTTPS
From the repository root:

```bash
curl --cacert secrets/portainer.crt --fail --show-error --max-time 10 https://localhost:9443/api/status
```

## Stop the project
```bash
docker compose --env-file .env -f demo/compose.yaml stop
docker compose --env-file .env -f compose.yaml stop
```

## Start again
```bash
bash scripts/deploy.sh
```

## Verified locally
- Portainer and demo application were accessible.
- HTTPS verification succeeded using the local certificate.
- Re-running init.sh preserved the contents of .env, the certificate,
  and its private key.
- Re-running deploy.sh succeeded, and the existing Portainer account
  and container view remained available.

## Remaining validation
- A clean installation from the GitHub branch has not yet been tested.
- Azure deployment has not yet been tested.
- Backup and restore were not tested in these checks.
