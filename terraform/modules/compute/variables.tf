variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "instance_profile_name" {
  type = string
}

variable "control_plane_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_type" {
  type    = string
  default = "t3.small"
}

variable "worker_count" {
  type    = number
  default = 2
}

variable "key_name" {
  type    = string
  default = ""
}

