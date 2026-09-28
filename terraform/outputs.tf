# Display the public IP address used by Portainer services and DNS
output "public_ip" {
  description = "Public IP address of the Portainer VM"
  value       = azurerm_public_ip.portainer.ip_address
}

# Display the private IP address of the VM inside the Azure VNet
output "private_ip" {
  description = "Private IP address of the Portainer VM"
  value       = azurerm_network_interface.portainer.private_ip_address
}

# Entra ID SSH command for administrators connected through the Point-to-Site VPN.
output "entra_ssh_command" {
  value = "az ssh vm --resource-group ${azurerm_resource_group.portainer.name} --name ${azurerm_linux_virtual_machine.portainer.name} --prefer-private-ip"
}