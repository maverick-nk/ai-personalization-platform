resource "google_artifact_registry_repository" "personalization" {
  location      = var.region
  repository_id = "personalization"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Docker images for the AI personalization platform"
}

resource "google_artifact_registry_repository_iam_member" "cicd_pusher" {
  location   = var.region
  repository = google_artifact_registry_repository.personalization.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:cicd-image-pusher@${var.project_id}.iam.gserviceaccount.com"
  project    = var.project_id
}
