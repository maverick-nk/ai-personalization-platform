terraform {
  backend "gcs" {
    bucket = "REPLACE_WITH_PROJECT_ID-tf-state-prod"
    prefix = "terraform/state"
  }
}
