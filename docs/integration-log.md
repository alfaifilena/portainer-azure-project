# Integration Log: Terraform VM + Portainer Deployment

This log records integrating the Terraform-provisioned Azure VM with the
Docker Compose deployment of Portainer.

## Environment

| Item | Value |
|---|---|
| Branch | integration/azure-portainer |
| VM OS | Ubuntu 22.04 (provisioned by Terraform) |
| VM user | Provided by infrastructure owner (not recorded here) |
| Access | SSH key only, source IP restricted by NSG |

## Steps performed

### 1. Merge Terraform into the integration branch
```bash
git merge --no-ff origin/feature/terraform-infrastructure -m "merge: terraform into integration/azure-portainer branch"
```
Result: `terraform/` folder added next to `scripts/` and `compose.yaml`.

### 2. Connect to the VM
```bash
ssh <USER>@<VM_PUBLIC_IP>
```
Result: Connected. Docker was not installed (clean VM, as expected).

### 3. Copy the committed code to the VM
```bash
git archive --format=tar HEAD | \
  ssh <USER>@<VM_PUBLIC_IP> "mkdir -p ~/portainer-azure-project && tar -x -C ~/portainer-azure-project"
```
Result: Project files present on the VM. `.env` and `secrets/` are not copied; they are generated on the VM.

### 4. Install Docker on the VM
```bash
sudo bash scripts/docker-install.sh
```
Result: Passed.
Note: Ubuntu 22.04 showed a "Daemons using outdated libraries" prompt; pressing Enter kept the defaults.

### 5. Initialize and deploy
```bash
sudo bash scripts/init.sh
sudo bash scripts/deploy.sh
```
Result: `Deployment checks passed: Portainer HTTPS and demo HTTP.`

### 6. First login through the SSH tunnel
```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 9443:127.0.0.1:9443 -L 8081:127.0.0.1:8081 \
  <USER>@<VM_PUBLIC_IP>
```
Opened `https://localhost:9443`, entered the setup token, created the admin account, skipped Edge Compute.
Result: Logged in to Portainer on the Azure VM.

## Security verification

| Check | Command | Result | Status |
|---|---|---|---|
| Portainer not reachable from the internet | `curl -k --max-time 5 https://<VM_PUBLIC_IP>:9443` (from local machine) | Connection timed out | Passed |

Portainer is protected by two layers: the NSG blocks inbound 9443, and
`compose.yaml` binds Portainer to `127.0.0.1` only.

## Issues found during integration

| Issue | Cause | Fix |
|---|---|---|
| "Daemons using outdated libraries" prompt during Docker install | Ubuntu 22.04 needrestart | Press Enter. Planned fix: set `DEBIAN_FRONTEND=noninteractive` and `NEEDRESTART_MODE=a` in `docker-install.sh` |
| "Timed out for security purposes" | Admin not created within ~5 minutes | `docker compose ... restart portainer`, then use the new token |
| 403 when creating the admin | Old or incorrectly copied setup token | Use the latest token line from the logs, copy only the token value |

## Remaining
- Verify ports are bound to `127.0.0.1` on the VM (`ss -tlnp`)
- Verify `.env` and `portainer.key` permissions are 600
- Portainer functional tests on `demo-web` (logs, stats, stop/start/restart)
- Redeploy test (secrets unchanged, same login)
- VM reboot test
- Host hardening test (`harden.sh`)
