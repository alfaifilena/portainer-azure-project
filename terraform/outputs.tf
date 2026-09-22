# Display the public IP address used to connect to the VM
output "public_ip" {
  description = "Public IP address of the Portainer VM"
  value       = azurerm_public_ip.portainer.ip_address
}

# Display the private IP address of the VM inside the Azure VNet
output "private_ip" {
  description = "Private IP address of the Portainer VM"
  value       = azurerm_network_interface.portainer.private_ip_address
}

# Generate the SSH command used to connect to the VM
output "ssh_command" {
  description = "SSH command to connect to the Portainer VM"
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.portainer.ip_address}"
}

# Generate the SSH tunnel command for Portainer and the demo application
output "ssh_tunnel_command" {
  description = "SSH tunnel command for Portainer and the demo application"
  value       = "ssh -N -L 9443:127.0.0.1:9443 -L 8081:127.0.0.1:8081 ${var.admin_username}@${azurerm_public_ip.portainer.ip_address}"
}
