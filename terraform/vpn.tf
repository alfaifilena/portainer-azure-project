# Read the current Microsoft Entra tenant information.
data "azuread_client_config" "current" {}

# Public IP used by the Azure VPN Gateway.
resource "azurerm_public_ip" "vpn_gateway" {
  name                = "pip-portainer-vpn"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  allocation_method = "Static"
  sku               = "Standard"

  tags = {
    project     = "CC-RCP-12"
    application = "Portainer"
    purpose     = "p2s-vpn"
  }
}

# Azure VPN Gateway used by Portainer administrators.
resource "azurerm_virtual_network_gateway" "portainer_vpn" {
  name                = "vgw-portainer"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  type       = "Vpn"
  vpn_type   = "RouteBased"
  sku        = "VpnGw1AZ"
  generation = "Generation1"

  active_active = false
  bgp_enabled   = false

  ip_configuration {
    name                          = "vpnGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.vpn_gateway.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }

  # Point-to-Site configuration for administrator devices.
  vpn_client_configuration {
    # Private IP addresses assigned to connected VPN clients.
    address_space = [
      "172.16.100.0/24"
    ]

    # Microsoft Entra ID authentication requires OpenVPN.
    vpn_client_protocols = [
      "OpenVPN"
    ]

    vpn_auth_types = [
      "AAD"
    ]


    # Microsoft Entra tenant used for authentication.
    aad_tenant = "https://login.microsoftonline.com/${data.azuread_client_config.current.tenant_id}"

    # Use our custom Portainer VPN application as the audience.
    aad_audience = azuread_application_registration.portainer_vpn.client_id

    # Microsoft Entra Security Token Service issuer.
    aad_issuer = "https://sts.windows.net/${data.azuread_client_config.current.tenant_id}/"
  }

  tags = {
    project     = "CC-RCP-12"
    application = "Portainer"
    purpose     = "admin-p2s-vpn"
  }
}