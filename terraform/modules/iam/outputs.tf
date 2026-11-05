output "instance_profile_name" {
  description = "IAM instance profile name to attach to EC2 instances"
  value       = var.use_aws_academy_lab_profile ? "LabInstanceProfile" : aws_iam_instance_profile.standard_profile[0].name
}

