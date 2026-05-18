resource "google_container_cluster" "primary" {
  name     = "${var.environment}-platform-cluster"
  project  = var.project_id
  location = var.location # zone for dev (free mgmt), region for prod

  # Remove the default node pool after creation — we manage our own pools below.
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = var.vpc_name
  subnetwork = var.subnet_name

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }

  # Private cluster: nodes have internal IPs only; egress via Cloud NAT.
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false # keep control plane reachable from internet for dev
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Disable legacy ABAC; RBAC only.
  enable_legacy_abac = false

  deletion_protection = var.environment == "prod" ? true : false
}

# On-demand node pool for Kafka — StatefulSet with PVCs, must not be preempted.
resource "google_container_node_pool" "kafka_ondemand" {
  name     = "kafka-ondemand"
  cluster  = google_container_cluster.primary.name
  project  = var.project_id
  location = var.location

  node_count = var.kafka_node_count

  node_config {
    machine_type = "e2-standard-2"
    disk_size_gb = 50
    disk_type    = "pd-ssd"

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Taint so only Kafka pods (with matching toleration) land here.
    taint {
      key    = "dedicated"
      value  = "kafka"
      effect = "NO_SCHEDULE"
    }

    labels = {
      environment = var.environment
      pool        = "kafka-ondemand"
    }
  }
}

# Spot node pool for all other workloads: stateless services, MLflow, Flink.
resource "google_container_node_pool" "apps_spot" {
  name     = "apps-spot"
  cluster  = google_container_cluster.primary.name
  project  = var.project_id
  location = var.location

  autoscaling {
    min_node_count = var.apps_min_nodes
    max_node_count = var.apps_max_nodes
  }

  node_config {
    machine_type = var.apps_machine_type
    disk_size_gb = 50
    disk_type    = "pd-balanced"

    # Spot VMs: ~60-91% cheaper than on-demand; pods tolerate preemption via
    # PodDisruptionBudgets, Flink GCS checkpointing, and HPA min=2.
    spot = true

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      environment = var.environment
      pool        = "apps-spot"
    }
  }
}
