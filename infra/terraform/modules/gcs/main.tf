resource "google_storage_bucket" "parquet" {
  name          = "${var.project_id}-parquet-${var.environment}"
  location      = var.region
  project       = var.project_id
  force_destroy = var.environment != "prod"

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }
}

resource "google_storage_bucket" "mlflow_artifacts" {
  name          = "${var.project_id}-mlflow-artifacts-${var.environment}"
  location      = var.region
  project       = var.project_id
  force_destroy = var.environment != "prod"

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }
}
