terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
variable "name" { type = string }
variable "tags" { type = map(string) }
variable "aws_region" { type = string }
variable "cidr" { type = string }
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(distinct(var.availability_zones)) == 2
    error_message = "Select exactly two distinct Availability Zones."
  }
}
variable "flow_log_role_arn" { type = string }
variable "logs_kms_key_arn" { type = string }
locals {
  zones = { for index, zone in var.availability_zones : tostring(index) => zone }
}
resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Component = "network" }, { Name = "${var.name}-vpc" })
}
resource "aws_default_security_group" "closed" {
  vpc_id  = aws_vpc.this.id
  tags    = merge(var.tags, { Component = "security" }, { Name = "${var.name}-default-deny" })
  ingress = []
  egress  = []
  # Empty rules deliberately close only this newly created VPC's default group.
}
resource "aws_subnet" "public" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.cidr, 8, tonumber(each.key))
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Component = "network" }, {
    Name                     = "${var.name}-public-${each.key}"
    "kubernetes.io/role/elb" = "1"
  })
}
resource "aws_subnet" "application" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.cidr, 4, 2 + tonumber(each.key))
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Component = "network" }, {
    Name                              = "${var.name}-application-${each.key}"
    "kubernetes.io/role/internal-elb" = "1"
  })
}
resource "aws_subnet" "database" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.cidr, 8, 64 + tonumber(each.key))
  map_public_ip_on_launch = false
  tags                    = merge(var.tags, { Component = "network" }, { Name = "${var.name}-database-${each.key}" })
}
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Component = "network" }, { Name = "${var.name}-igw" })
}
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = merge(var.tags, { Component = "network" }, { Name = "${var.name}-nat-eip" })
}
resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public["0"].id
  depends_on    = [aws_internet_gateway.this]
  tags          = merge(var.tags, { Component = "network" }, { Name = "${var.name}-nat" })
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Component = "network" }, { Name = "${var.name}-public" })
}
resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}
resource "aws_route_table_association" "public" {
  for_each       = local.zones
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}
resource "aws_route_table" "application" {
  for_each = local.zones
  vpc_id   = aws_vpc.this.id
  tags     = merge(var.tags, { Component = "network" }, { Name = "${var.name}-application-${each.key}" })
}
resource "aws_route" "nat" {
  for_each               = local.zones
  route_table_id         = aws_route_table.application[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this.id
}
resource "aws_route_table_association" "application" {
  for_each       = local.zones
  subnet_id      = aws_subnet.application[each.key].id
  route_table_id = aws_route_table.application[each.key].id
}
resource "aws_route_table" "database" {
  for_each = local.zones
  vpc_id   = aws_vpc.this.id
  tags     = merge(var.tags, { Component = "network" }, { Name = "${var.name}-isolated-database-${each.key}" })
  route    = []
  # Local VPC route only: no Internet Gateway or NAT default route.
}
resource "aws_route_table_association" "database" {
  for_each       = local.zones
  subnet_id      = aws_subnet.database[each.key].id
  route_table_id = aws_route_table.database[each.key].id
}
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for table in aws_route_table.application : table.id]
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid    = "RegionalECRLayersOnly", Effect = "Allow", Principal = "*",
    Action = ["s3:GetObject"], Resource = ["arn:aws:s3:::prod-${var.aws_region}-starport-layer-bucket/*"]
  }] })
  tags = merge(var.tags, { Component = "network" }, { Name = "${var.name}-s3" })
}
resource "aws_cloudwatch_log_group" "flow" {
  tags = merge(var.tags, { Component = "logging", Name = "${var.name}-flow-logs" })
  # checkov:skip=CKV_AWS_338:Development flow logs retain 30 days; annual retention is reviewed in Phase 6.
  name              = "/banking/${var.name}/vpc-flow"
  retention_in_days = 30
  kms_key_id        = var.logs_kms_key_arn
}
resource "aws_flow_log" "this" {
  tags                 = merge(var.tags, { Component = "logging", Name = "${var.name}-vpc-flow" })
  vpc_id               = aws_vpc.this.id
  traffic_type         = "ALL"
  iam_role_arn         = var.flow_log_role_arn
  log_destination_type = "cloud-watch-logs"
  log_destination      = aws_cloudwatch_log_group.flow.arn
}
output "vpc_id" { value = aws_vpc.this.id }
output "public_subnet_ids" { value = [for subnet in aws_subnet.public : subnet.id] }
output "application_subnet_ids" { value = [for subnet in aws_subnet.application : subnet.id] }
output "database_subnet_ids" { value = [for subnet in aws_subnet.database : subnet.id] }

output "default_security_group_id" { value = aws_vpc.this.default_security_group_id }
