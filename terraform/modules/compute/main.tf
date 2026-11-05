data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

locals {
  user_data_base = <<-EOF
    #!/bin/bash
    sudo swapoff -a
    sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
    cat <<K8SCONF | sudo tee /etc/modules-load.d/k8s.conf
    overlay
    br_netfilter
    K8SCONF
    sudo modprobe overlay
    sudo modprobe br_netfilter
    cat <<SYSCTL | sudo tee /etc/sysctl.d/k8s.conf
    net.bridge.bridge-nf-call-iptables  = 1
    net.bridge.bridge-nf-call-ip6tables = 1
    net.ipv4.ip_forward                 = 1
    SYSCTL
    sudo sysctl --system
  EOF
}

# Control Plane Node (t3.medium)
resource "aws_instance" "control_plane" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.control_plane_type
  subnet_id            = var.subnet_ids[0]
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile = var.instance_profile_name
  key_name             = var.key_name != "" ? var.key_name : null

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data = local.user_data_base

  tags = {
    Name = "k8s-control-plane"
    Role = "control-plane"
  }
}

# Worker Nodes (t3.small)
resource "aws_instance" "workers" {
  count                = var.worker_count
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.worker_type
  subnet_id            = var.subnet_ids[count.index % length(var.subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile = var.instance_profile_name
  key_name             = var.key_name != "" ? var.key_name : null

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data = local.user_data_base

  tags = {
    Name = "k8s-worker-${count.index + 1}"
    Role = "worker"
  }
}

