mock_provider "aws" {
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-2:123456789012:log-group:/banking/banking-dev/vpc-flow" }
  }
}
variables {
  aws_region         = "us-east-2"
  tags               = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform", Owner = "TestOwner", Purpose = "CloudEngineerTraining" }
  name               = "banking-dev"
  cidr               = "10.70.0.0/16"
  availability_zones = ["us-east-2a", "us-east-2b"]
  flow_log_role_arn  = "arn:aws:iam::123456789012:role/test-flow"
  logs_kms_key_arn   = "arn:aws:kms:us-east-2:123456789012:key/00000000-0000-0000-0000-000000000000"
}
run "private_network" {
  command = plan
  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.application) == 2 && length(aws_subnet.database) == 2
    error_message = "Every tier must span two AZs."
  }
  assert {
    condition     = alltrue([for subnet in merge(aws_subnet.public, aws_subnet.application, aws_subnet.database) : !subnet.map_public_ip_on_launch])
    error_message = "Instances must not receive automatic public addresses."
  }
  assert {
    condition     = aws_subnet.application["0"].cidr_block == "10.70.32.0/20" && aws_subnet.application["1"].cidr_block == "10.70.48.0/20" && aws_subnet.database["0"].cidr_block == "10.70.64.0/24"
    error_message = "Derived application and database ranges must not overlap."
  }
  assert {
    condition     = length(aws_route_table.database["0"].route) == 0 && length(aws_route_table.database["1"].route) == 0
    error_message = "Database route tables have no external route."
  }
  assert {
    condition     = length(aws_default_security_group.closed.ingress) == 0 && length(aws_default_security_group.closed.egress) == 0
    error_message = "The new VPC default security group must deny traffic."
  }
}
run "duplicate_zone_rejected" {
  command = plan
  variables { availability_zones = ["us-east-2a", "us-east-2a"] }
  expect_failures = [var.availability_zones]
}
run "routing_connections" {
  command = apply
  assert {
    condition = (aws_nat_gateway.this.subnet_id == aws_subnet.public["0"].id &&
      aws_route.internet.gateway_id == aws_internet_gateway.this.id &&
      alltrue([for route in aws_route.nat : route.nat_gateway_id == aws_nat_gateway.this.id]) &&
      alltrue([for key, link in aws_route_table_association.application : link.subnet_id == aws_subnet.application[key].id && link.route_table_id == aws_route_table.application[key].id]) &&
      alltrue([for key, link in aws_route_table_association.public : link.subnet_id == aws_subnet.public[key].id && link.route_table_id == aws_route_table.public.id]) &&
      alltrue([for key, link in aws_route_table_association.database : link.subnet_id == aws_subnet.database[key].id && link.route_table_id == aws_route_table.database[key].id]) &&
    aws_vpc_endpoint.s3.route_table_ids == toset([for table in aws_route_table.application : table.id]))
    error_message = "NAT/IGW, every tier association and S3 endpoint must connect to the intended resources."
  }
}
