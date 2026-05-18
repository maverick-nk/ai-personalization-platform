resource "google_redis_instance" "main" {
  name           = "${var.environment}-platform-redis"
  tier           = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.environment == "prod" ? 4 : 1
  region         = var.region
  project        = var.project_id

  redis_version     = "REDIS_7_0"
  display_name      = "${var.environment} platform Redis"
  authorized_network = var.vpc_id

  connect_mode = "PRIVATE_SERVICE_ACCESS"

  depends_on = [var.private_vpc_connection]
}
