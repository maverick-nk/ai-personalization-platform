resource "google_artifact_registry_repository" "personalization" {
  location      = var.region
  repository_id = "personalization"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Docker images for the AI personalization platform"
}
