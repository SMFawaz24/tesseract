variable "aws_region" {
  description = "AWS Region to deploy infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the Kubernetes cluster VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "control_plane_instance_type" {
  description = "EC2 instance type for the Control Plane (requires >= 2 vCPU, >= 3GB RAM)"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for the Worker nodes"
  type        = string
  default     = "t3.small"
}

variable "worker_count" {
  description = "Number of worker nodes to launch"
  type        = number
  default     = 2
}

variable "key_name" {
  description = "Name of the EC2 key pair for SSH access (leave empty if using EC2 Instance Connect)"
  type        = string
  default     = ""
}

variable "use_aws_academy_lab_profile" {
  description = "Set to true if deploying in AWS Academy Learner Lab to use pre-existing LabInstanceProfile"
  type        = bool
  default     = true
}

