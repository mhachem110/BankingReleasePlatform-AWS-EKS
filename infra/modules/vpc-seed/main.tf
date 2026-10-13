terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
variable "name" { type = string }
variable "cidr" { type = string }
variable "tags" { type = map(string) }
# Keep this configuration identical to modules/network's VPC. The first
# protected apply writes its final platform address into the platform state.
resource "aws_vpc" "this" {
  # checkov:skip=CKV2_AWS_11:No workloads/subnets exist in this seed; the full platform adds encrypted VPC flow logs before workloads.
  # checkov:skip=CKV2_AWS_12:This seed exposes nothing; the full platform closes its exact default group before workloads.
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Component = "network" }, { Name = "${var.name}-vpc" })
  lifecycle { prevent_destroy = true }
}
output "vpc_id" { value = aws_vpc.this.id }
output "default_security_group_id" { value = aws_vpc.this.default_security_group_id }
