variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "nodes_cidr" { type = string; default = "10.0.0.0/20" }
variable "pods_cidr" { type = string; default = "10.1.0.0/16" }
variable "services_cidr" { type = string; default = "10.2.0.0/20" }
