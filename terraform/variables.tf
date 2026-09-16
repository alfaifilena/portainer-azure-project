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

variable "admin_cidrs" {
  description = "Public IPv4 addresses allowed to connect through SSH, in /32 CIDR format"
  type        = list(string)

  validation {
    condition = length(var.admin_cidrs) > 0 && alltrue([
      for cidr in var.admin_cidrs :
      can(cidrhost(cidr, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", cidr))
    ])

    error_message = "Each admin CIDR must be a valid IPv4 address using /32, for example 203.0.113.10/32."
  }
}