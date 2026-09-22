# Create the Azure Resource Group that will contain all project resources
resource "azurerm_resource_group" "portainer" {
  name     = "rg-portainer"
  location = var.location

  tags = {
    project     = "CC-RCP-12"
    application = "Portainer"
    environment = "internal"
  }
}

# Create the Virtual Network for the Portainer environment
resource "azurerm_virtual_network" "portainer" {
  name                = "vnet-portainer"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  address_space = ["10.10.0.0/16"]

  tags = {
    project = "CC-RCP-12"
  }
}

# Create a subnet inside the Virtual Network for the Linux VM
resource "azurerm_subnet" "portainer" {
  name                 = "subnet-portainer"
  resource_group_name  = azurerm_resource_group.portainer.name
  virtual_network_name = azurerm_virtual_network.portainer.name

  address_prefixes = ["10.10.1.0/24"]
}

# Create a Network Security Group to control inbound network traffic
resource "azurerm_network_security_group" "portainer" {
  name                = "nsg-portainer"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  # Allow SSH access only from approved administrator public IP addresses
  security_rule {
    name                       = "Allow-SSH-From-Admins"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.admin_cidrs
    destination_address_prefix = "*"
  }

  tags = {
    project = "CC-RCP-12"
  }
}

# Create a static public IP address for SSH access to the VM
resource "azurerm_public_ip" "portainer" {
  name                = "pip-portainer"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  allocation_method = "Static"
  sku               = "Standard"

  domain_name_label = "portainer-container-hub"

  tags = {
    project = "CC-RCP-12"
  }
}

# Create the network interface that connects the VM to the subnet and public IP
resource "azurerm_network_interface" "portainer" {
  name                = "nic-portainer"
  location            = azurerm_resource_group.portainer.location
  resource_group_name = azurerm_resource_group.portainer.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.portainer.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.portainer.id
  }

  tags = {
    project = "CC-RCP-12"
  }
}

# Attach the Network Security Group to the VM network interface
resource "azurerm_network_interface_security_group_association" "portainer" {
  network_interface_id      = azurerm_network_interface.portainer.id
  network_security_group_id = azurerm_network_security_group.portainer.id
}

# Create the Ubuntu Linux VM that will host Docker and Portainer
resource "azurerm_linux_virtual_machine" "portainer" {
  name                = "vm-portainer"
  resource_group_name = azurerm_resource_group.portainer.name
  location            = azurerm_resource_group.portainer.location
  size                = var.vm_size
  admin_username      = var.admin_username

  # Disable password login so SSH key authentication is required
  disable_password_authentication = true

  network_interface_ids = [
    azurerm_network_interface.portainer.id
  ]

  # Add the administrator SSH public key to the VM
  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  # Configure the operating system disk
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  # Use Ubuntu Server as the VM operating system
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  tags = {
    project     = "CC-RCP-12"
    application = "Portainer"
    environment = "internal"
  }
}

# Create a persistent managed data disk for Docker and Portainer data
resource "azurerm_managed_disk" "portainer_data" {
  name                 = "disk-portainer-data"
  location             = azurerm_resource_group.portainer.location
  resource_group_name  = azurerm_resource_group.portainer.name
  storage_account_type = "StandardSSD_LRS"
  create_option        = "Empty"
  disk_size_gb         = 32

  tags = {
    project     = "CC-RCP-12"
    application = "Portainer"
    purpose     = "persistent-data"
  }
}

# Attach the persistent data disk to the Portainer VM
resource "azurerm_virtual_machine_data_disk_attachment" "portainer_data" {
  managed_disk_id    = azurerm_managed_disk.portainer_data.id
  virtual_machine_id = azurerm_linux_virtual_machine.portainer.id
  lun                = 0
  caching            = "None"
}