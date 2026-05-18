terraform {
  backend "gcs" {
    bucket = "REPLACE_WITH_PROJECT_ID-tf-state-dev"
    prefix = "terraform/state"
  }
}
