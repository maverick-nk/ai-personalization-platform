output "parquet_bucket" { value = google_storage_bucket.parquet.name }
output "mlflow_artifacts_bucket" { value = google_storage_bucket.mlflow_artifacts.name }
