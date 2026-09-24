data "azuread_users" "existing_portainer_admins" {
  user_principal_names = var.portainer_admin_upns
}

resource "azuread_invitation" "portainer_admin_guests" {
  for_each = toset(var.portainer_admin_guest_emails)

  user_email_address = each.value
  redirect_url       = "https://portal.azure.com"
}

resource "azuread_group" "portainer_admins" {
  display_name     = "Portainer-Admins"
  security_enabled = true

  members = concat(
    data.azuread_users.existing_portainer_admins.object_ids,
    [for guest in azuread_invitation.portainer_admin_guests : guest.user_id]
  )
}

resource "azurerm_virtual_machine_extension" "aad_ssh_login" {
  name                 = "AADSSHLoginForLinux"
  virtual_machine_id   = azurerm_linux_virtual_machine.portainer.id
  publisher            = "Microsoft.Azure.ActiveDirectory"
  type                 = "AADSSHLoginForLinux"
  type_handler_version = "1.0"

  auto_upgrade_minor_version = true
}

resource "azurerm_role_assignment" "portainer_admin_vm_login" {
  scope                = azurerm_resource_group.portainer.id
  role_definition_name = "Virtual Machine Administrator Login"
  principal_id         = azuread_group.portainer_admins.object_id
  principal_type       = "Group"
}

# ------------------------------------------------------------
# Custom Microsoft Entra application for Portainer Admin VPN
# ------------------------------------------------------------

locals {
  # Microsoft-registered Azure VPN Client application ID.
  azure_vpn_client_id = "c632b3df-fb67-4d84-bdcf-b95ad541b5c8"

  # Stable ID for the custom VPN permission scope.
  portainer_vpn_scope_id = "2de0d9be-7c6d-4acb-9d3d-6ad84ef70f9d"
}

# Register a custom application that will be used as the
# VPN Gateway audience.
resource "azuread_application_registration" "portainer_vpn" {
  display_name     = "Portainer Admin VPN"
  sign_in_audience = "AzureADMyOrg"
}

# Give the application an API identifier URI.
resource "azuread_application_identifier_uri" "portainer_vpn" {
  application_id = azuread_application_registration.portainer_vpn.id
  identifier_uri = "api://${azuread_application_registration.portainer_vpn.client_id}"
}

# Expose a delegated permission used by Azure VPN Client.
resource "azuread_application_permission_scope" "portainer_vpn" {
  application_id = azuread_application_registration.portainer_vpn.id
  scope_id       = local.portainer_vpn_scope_id
  value          = "Portainer-VPN-Access"

  type = "Admin"

  admin_consent_display_name = "Access Portainer Admin VPN"
  admin_consent_description  = "Allow authorized administrators to access the Portainer P2S VPN."

  user_consent_display_name = "Access Portainer Admin VPN"
  user_consent_description  = "Allow access to the Portainer P2S VPN."
}

# Pre-authorize the official Microsoft Azure VPN Client
# only after the custom VPN permission scope has been created.
resource "azuread_application_pre_authorized" "azure_vpn_client" {
  application_id       = azuread_application_registration.portainer_vpn.id
  authorized_client_id = local.azure_vpn_client_id

  permission_ids = [
    azuread_application_permission_scope.portainer_vpn.scope_id
  ]

  depends_on = [
    azuread_application_permission_scope.portainer_vpn
  ]
}

# Create the Enterprise Application for the custom VPN app.
# Assignment is required, so unassigned users cannot authenticate.
resource "azuread_service_principal" "portainer_vpn" {
  client_id                    = azuread_application_registration.portainer_vpn.client_id
  app_role_assignment_required = true
}

# Assign only the Portainer-Admins Entra group to the VPN application.
resource "azuread_app_role_assignment" "portainer_admins_vpn" {
  app_role_id         = "00000000-0000-0000-0000-000000000000"
  principal_object_id = azuread_group.portainer_admins.object_id
  resource_object_id  = azuread_service_principal.portainer_vpn.object_id
}