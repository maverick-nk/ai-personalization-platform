terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  # Reads GOOGLE_IMPERSONATE_SERVICE_ACCOUNT from the environment.
  # Set it to terraform-operator@<project>.iam.gserviceaccount.com before running
  # terraform apply. SA key files are not used; see infra/DEPLOYMENT.md §1.3.
  impersonate_service_account = var.impersonate_service_account
}

locals {
  environment = "dev"
}

module "networking" {
  source      = "../../modules/networking"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
}

module "gke" {
  source              = "../../modules/gke"
  project_id          = var.project_id
  environment         = local.environment
  location            = var.zone # zonal for dev — free cluster management fee
  vpc_name            = module.networking.vpc_name
  subnet_name         = module.networking.subnet_name
  pods_range_name     = module.networking.pods_range_name
  services_range_name = module.networking.services_range_name
  kafka_node_count    = 1
  apps_min_nodes      = 2
  apps_max_nodes      = 5
  apps_machine_type   = "e2-standard-2"
}

module "cloud_sql" {
  source                 = "../../modules/cloud-sql"
  project_id             = var.project_id
  region                 = var.region
  environment            = local.environment
  vpc_id                 = module.networking.vpc_id
  private_vpc_connection = module.networking.private_vpc_connection
  tier                   = "db-f1-micro"
}

module "memorystore" {
  source                 = "../../modules/memorystore"
  project_id             = var.project_id
  region                 = var.region
  environment            = local.environment
  vpc_id                 = module.networking.vpc_id
  private_vpc_connection = module.networking.private_vpc_connection
}

module "artifact_registry" {
  source     = "../../modules/artifact-registry"
  project_id = var.project_id
  region     = var.region
}

module "gcs" {
  source      = "../../modules/gcs"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
}

output "gke_cluster_name" { value = module.gke.cluster_name }
output "repository_url" { value = module.artifact_registry.repository_url }
output "parquet_bucket" { value = module.gcs.parquet_bucket }
output "mlflow_artifacts_bucket" { value = module.gcs.mlflow_artifacts_bucket }
output "redis_host" { value = module.memorystore.host }
output "redis_port" { value = module.memorystore.port }
output "cloud_sql_instance" { value = module.cloud_sql.instance_name }
output "cloud_sql_private_ip" { value = module.cloud_sql.private_ip }
output "privacy_db_url" { value = module.cloud_sql.privacy_db_url; sensitive = true }
output "mlflow_db_url" { value = module.cloud_sql.mlflow_db_url; sensitive = true }
