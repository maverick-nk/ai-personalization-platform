variable "project_id" { type = string }
variable "environment" { type = string }
variable "location" { type = string } # zone (dev) or region (prod)
variable "vpc_name" { type = string }
variable "subnet_name" { type = string }
variable "pods_range_name" { type = string }
variable "services_range_name" { type = string }
variable "kafka_node_count" { type = number; default = 1 }
variable "apps_min_nodes" { type = number; default = 2 }
variable "apps_max_nodes" { type = number; default = 5 }
variable "apps_machine_type" { type = string; default = "e2-standard-2" }
