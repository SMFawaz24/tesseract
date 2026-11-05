# ==============================================================================
# ROOT MODULE: Orchestrates Network, Storage, IAM, and Compute
# ==============================================================================

module "network" {
  source              = "./modules/network"
  vpc_cidr            = var.vpc_cidr
  public_subnet_cidrs = var.public_subnet_cidrs
  aws_region          = var.aws_region
}

module "storage" {
  source     = "./modules/storage"
  aws_region = var.aws_region
}

module "iam" {
  source                      = "./modules/iam"
  use_aws_academy_lab_profile = var.use_aws_academy_lab_profile
  s3_bucket_arn               = module.storage.bucket_arn
}

module "compute" {
  source                = "./modules/compute"
  subnet_ids            = module.network.public_subnet_ids
  security_group_id     = module.network.security_group_id
  instance_profile_name = module.iam.instance_profile_name
  control_plane_type    = var.control_plane_instance_type
  worker_type           = var.worker_instance_type
  worker_count          = var.worker_count
  key_name              = var.key_name
}

