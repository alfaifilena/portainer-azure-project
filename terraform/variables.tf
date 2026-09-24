variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string

  validation {
    condition     = length(trimspace(var.subscription_id)) > 0
    error_message = "Azure subscription ID must not be empty."
  }
}

variable "location" {
  description = "Azure region where resources will be deployed"
  type        = string
  default     = "eastus"

  validation {
    condition     = can(regex("^[a-z0-9]+$", var.location))
    error_message = "Location must be a valid Azure region name such as eastus or westeurope."
  }
}

variable "vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"

  validation {
    condition     = startswith(var.vm_size, "Standard_")
    error_message = "VM size must be a valid Azure Standard VM size."
  }
}

variable "admin_username" {
  description = "Administrator username for the Linux VM"
  type        = string
  default     = "azureadmin"

  validation {
    condition     = length(var.admin_username) >= 3
    error_message = "Administrator username must contain at least 3 characters."
  }
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key"
  type        = string

  validation {
    condition     = length(trimspace(var.ssh_public_key_path)) > 0
    error_message = "SSH public key path must not be empty."
  }
}

variable "portainer_admin_upns" {
  description = "Existing Microsoft Entra admin UPNs"
  type        = list(string)
  default     = []
}

variable "portainer_admin_guest_emails" {
  description = "External admin emails to invite as guests"
  type        = list(string)
  default     = []
}