output "instance_name" { value = google_sql_database_instance.main.name }
output "private_ip" { value = google_sql_database_instance.main.private_ip_address }
output "privacy_db_url" {
  value     = "postgresql://privacy_user:${random_password.privacy_user_password.result}@${google_sql_database_instance.main.private_ip_address}/privacy"
  sensitive = true
}
output "mlflow_db_url" {
  value     = "postgresql://mlflow_user:${random_password.mlflow_user_password.result}@${google_sql_database_instance.main.private_ip_address}/mlflow"
  sensitive = true
}
