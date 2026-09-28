# Container Hub

## 1. Project Summary

**Container Hub** is a cloud-based container management platform built using Microsoft Azure, Portainer, Docker, Terraform, and Python.

The platform provides centralized Docker container management, secure remote administration, remote environment management, persistent cloud storage, automated operational tools, continuous monitoring, notifications, and an administrator-only monitoring dashboard with optional AI-assisted analysis.

### System Architecture

![Container Hub Architecture](docs/assets/container-hub-architecture.png)

### Portainer Environment Management

![Portainer Environments](docs/assets/portainer-environments.png)

### Administrator Monitoring Dashboard

![AI Monitoring Dashboard](docs/assets/ai-dashboard.png)

### Main Capabilities

- Centralized Docker container management using Portainer CE
- Remote Docker environment management using Portainer Edge Agent
- Microsoft Azure cloud infrastructure
- Infrastructure provisioning using Terraform
- Secure HTTPS access through Nginx and Let's Encrypt
- Microsoft Entra ID authentication for infrastructure administrators
- Azure Point-to-Site VPN for secure SSH administration
- Persistent Docker and Portainer data using Azure Managed Disk
- Automated backup and restore
- Deployment, remote deployment, health-check, and hardening scripts
- Rule-based container monitoring
- Administrator-only Streamlit monitoring dashboard
- Optional AI-assisted analysis using Groq
- Telegram alerts and notifications
- Configurable container recovery

---

## 2. Requirements

The following tools and services are required to deploy and operate the project:

- Microsoft Azure subscription
- Docker Engine
- Docker Compose
- Portainer CE
- Terraform
- Azure CLI
- Git
- Python 3
- Nginx
- Microsoft Entra ID

The dashboard Python dependency is:

```text
streamlit==1.64.0
```

Install the Python dependency using:

```bash
pip install -r dashboard/requirements.txt
```

---

## 3. Installation

### Clone the Repository

```bash
git clone https://github.com/alfaifilena/portainer-azure-project.git
cd portainer-azure-project
```

### Configure Terraform

Navigate to the Terraform directory:

```bash
cd terraform
```

Initialize Terraform:

```bash
terraform init
```

Use:

```text
terraform.tfvars.example
```

as a template to create a local:

```text
terraform.tfvars
```

Review the infrastructure plan:

```bash
terraform plan
```

Deploy the Azure infrastructure:

```bash
terraform apply
```

### Configure Application Settings

Return to the project root and use:

```text
.env.example
```

as the template for local environment configuration.

Real passwords, API keys, private keys, and other secrets must not be committed to the repository.

---

## 4. Run the Project

### Start the Main Container Hub Stack

From the project root:

```bash
docker compose up -d
```

### Start the Monitoring Service

```bash
docker compose -f compose.monitor.yaml up -d --build
```

### Start the Administrator Dashboard

```bash
docker compose -f compose.dashboard.yaml up -d --build
```

### Verify Running Containers

```bash
docker ps
```

### Verify Docker Compose Services

```bash
docker compose ps
```

Portainer provides the main web interface for container and environment management.

The Streamlit monitoring dashboard is restricted to administrators.

---

## 5. API Keys & Environment Variables

Environment-specific configuration must be stored outside the source code.

Use:

```text
.env.example
```

as the application configuration template.

Depending on the enabled features, configuration may include:

- Portainer connection settings
- Groq API credentials
- Telegram Bot credentials
- Monitoring configuration
- Container recovery settings

Terraform-specific configuration should be stored locally in:

```text
terraform.tfvars
```

The following files must not be committed to Git:

```text
.env
terraform.tfvars
terraform.tfstate
terraform.tfstate.backup
.terraform/
*.tfplan
```

Only example files such as:

```text
.env.example
terraform.tfvars.example
```

should be included in source control.

The monitoring system uses SQLite for runtime persistence. The database is created automatically by the monitoring service and is not included as a project dataset.

---

## 6. Known Issues

- Some external networks may block or interfere with Portainer Edge Agent WebSocket traffic.
- AI-assisted analysis requires internet connectivity and valid Groq credentials.
- Telegram notifications require valid Telegram Bot configuration.
- Environment-specific values must be configured before deployment.
- The current automatic recovery mechanism is designed for a single Docker host and does not provide multi-host automatic failover.
- Backups stored on the same Azure Managed Disk support recovery but are not a replacement for an independent external backup.
