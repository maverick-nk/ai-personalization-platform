resource "google_sql_database_instance" "main" {
  name             = "${var.environment}-platform-pg"
  database_version = "POSTGRES_16"
  region           = var.region
  project          = var.project_id

  # Prevent accidental deletion in prod.
  deletion_protection = var.environment == "prod" ? true : false

  settings {
    tier              = var.tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    disk_size         = 10
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    ip_configuration {
      ipv4_enabled                                  = false # private IP only
      private_network                               = var.vpc_id
      enable_private_path_for_google_cloud_services = true
    }
  }

  depends_on = [var.private_vpc_connection]
}

resource "google_sql_database" "privacy" {
  name     = "privacy"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}

resource "google_sql_database" "mlflow" {
  name     = "mlflow"
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}

resource "random_password" "privacy_user_password" {
  length  = 32
  special = false
}

resource "random_password" "mlflow_user_password" {
  length  = 32
  special = false
}

resource "google_sql_user" "privacy_user" {
  name     = "privacy_user"
  instance = google_sql_database_instance.main.name
  password = random_password.privacy_user_password.result
  project  = var.project_id
}

resource "google_sql_user" "mlflow_user" {
  name     = "mlflow_user"
  instance = google_sql_database_instance.main.name
  password = random_password.mlflow_user_password.result
  project  = var.project_id
}
