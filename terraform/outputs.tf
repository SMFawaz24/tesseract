output "control_plane_public_ip" {
  description = "Public IP of the Control Plane node (use for SSH / Dashboard access)"
  value       = module.compute.control_plane_public_ip
}

output "worker_public_ips" {
  description = "Public IPs of the Kubernetes worker nodes"
  value       = module.compute.worker_public_ips
}

output "s3_bucket_name" {
  description = "Name of the encrypted S3 bucket storing decision logs and benchmarks"
  value       = module.storage.bucket_name
}

output "security_group_id" {
  description = "Security Group ID for the cluster"
  value       = module.network.security_group_id
}

output "vpc_id" {
  description = "VPC ID of the Kubernetes cluster"
  value       = module.network.vpc_id
}

