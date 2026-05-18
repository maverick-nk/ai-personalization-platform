variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_vpc_connection" { type = string } # dependency handle
variable "tier" { type = string; default = "db-f1-micro" } # override to db-g1-small for prod
