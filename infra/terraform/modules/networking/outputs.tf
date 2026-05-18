output "vpc_id" { value = google_compute_network.vpc.id }
output "vpc_name" { value = google_compute_network.vpc.name }
output "subnet_id" { value = google_compute_subnetwork.gke_nodes.id }
output "subnet_name" { value = google_compute_subnetwork.gke_nodes.name }
output "pods_range_name" { value = "gke-pods" }
output "services_range_name" { value = "gke-services" }
output "ingress_ip" { value = google_compute_global_address.ingress_ip.address }
output "private_vpc_connection" { value = google_service_networking_connection.private_vpc_connection.id }
