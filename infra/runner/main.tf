terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}

variable "state_bucket_name" { type = string }
variable "github_connection_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:codeconnections:us-east-2:866934333672:connection/[a-f0-9-]{36}$", var.github_connection_arn))
    error_message = "Supply the actual approved Ohio GitHub App connection ARN for this account."
  }
}
variable "aws_region" {
  type    = string
  default = "us-east-2"
  validation {
    condition     = var.aws_region == "us-east-2"
    error_message = "The Banking runner must stay in the approved Region."
  }
}
variable "expected_account_id" {
  type    = string
  default = "866934333672"
  validation {
    condition     = var.expected_account_id == "866934333672"
    error_message = "The Banking runner must stay in the approved account."
  }
}

locals {
  name = "banking-release-deployer"
  tags = {
    Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform",
    Owner   = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "ephemeral-runner"
  }
  role_arn    = "arn:aws:iam::${var.expected_account_id}:role/cloudbatch818-mahmoud-banking-codebuild-runner"
  project_arn = "arn:aws:codebuild:${var.aws_region}:${var.expected_account_id}:project/${local.name}"
  log_arn     = "arn:aws:logs:${var.aws_region}:${var.expected_account_id}:log-group:/banking/banking-dev/codebuild:*"
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags { tags = local.tags }
}

data "aws_caller_identity" "current" {}
data "terraform_remote_state" "platform" {
  backend = "s3"
  config = {
    bucket              = var.state_bucket_name
    key                 = "banking-release-platform/dev/platform/terraform.tfstate"
    region              = var.aws_region
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = [var.expected_account_id]
  }
}
data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket              = var.state_bucket_name
    key                 = "banking-release-platform/shared/runtime-foundation/terraform.tfstate"
    region              = var.aws_region
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = [var.expected_account_id]
  }
}

resource "terraform_data" "scope" {
  lifecycle {
    precondition {
      condition = (
        data.aws_caller_identity.current.account_id == var.expected_account_id &&
        data.terraform_remote_state.platform.outputs.cluster_name == "banking-dev" &&
        length(data.terraform_remote_state.platform.outputs.application_subnet_ids) == 2 &&
        startswith(data.terraform_remote_state.foundation.outputs.kms_key_arn, "arn:aws:kms:${var.aws_region}:${var.expected_account_id}:key/")
      )
      error_message = "The verified Banking platform state and two private application subnets are required."
    }
  }
}

# The service role has only ENI/logging rights. GitHub jobs obtain separate,
# short-lived OIDC sessions after their protected environment review.
locals {
  runner_permissions = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "VpcNetworkInterfaces", Effect = "Allow"
        Action    = ["ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeDhcpOptions", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeVpcs"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } }
      },
      {
        Sid      = "ShareOnlyBankingRunnerInterfaces", Effect = "Allow"
        Action   = "ec2:CreateNetworkInterfacePermission"
        Resource = "arn:aws:ec2:${var.aws_region}:${var.expected_account_id}:network-interface/*"
        Condition = {
          StringEquals = { "ec2:AuthorizedService" = "codebuild.amazonaws.com" }
          ArnEquals    = { "ec2:Subnet" = [for id in data.terraform_remote_state.platform.outputs.application_subnet_ids : "arn:aws:ec2:${var.aws_region}:${var.expected_account_id}:subnet/${id}"] }
        }
      },
      {
        Sid      = "RunnerLogs", Effect = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = local.log_arn
      },
      {
        Sid      = "OnlyApprovedGitHubConnection", Effect = "Allow"
        Action   = ["codeconnections:GetConnection", "codeconnections:GetConnectionToken"]
        Resource = var.github_connection_arn
      }
    ]
  })
}

resource "aws_iam_policy" "boundary" {
  name        = "cloudbatch818-mahmoud-banking-codebuild-runner-boundary"
  description = "Maximum service permissions for the ephemeral Banking CodeBuild runner"
  policy      = local.runner_permissions
  tags        = merge(local.tags, { Name = "${local.name}-boundary" })
  depends_on  = [terraform_data.scope]
  lifecycle { prevent_destroy = true }
}

resource "aws_iam_role" "runner" {
  name                 = "cloudbatch818-mahmoud-banking-codebuild-runner"
  permissions_boundary = aws_iam_policy.boundary.arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "codebuild.amazonaws.com" }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.expected_account_id }
        ArnEquals    = { "aws:SourceArn" = local.project_arn }
      }
    }]
  })
  tags = merge(local.tags, { Name = "${local.name}-service-role" })
  lifecycle { prevent_destroy = true }
}

resource "aws_iam_role_policy" "runner" {
  name   = "banking-codebuild-vpc-and-logs"
  role   = aws_iam_role.runner.id
  policy = local.runner_permissions
}

resource "aws_security_group" "runner" {
  name        = "${local.name}-private"
  description = "Outbound-only ephemeral runner to private EKS API and HTTPS services"
  vpc_id      = data.terraform_remote_state.platform.outputs.vpc_id
  tags        = merge(local.tags, { Name = "${local.name}-private" })
  depends_on  = [terraform_data.scope]
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.runner.id
  description       = "HTTPS to GitHub, AWS APIs and the private EKS control plane"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
  tags              = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "eks_api" {
  security_group_id            = data.terraform_remote_state.platform.outputs.cluster_security_group_id
  description                  = "HTTPS from the dedicated private CodeBuild runner only"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.runner.id
  tags                         = local.tags
}

resource "aws_cloudwatch_log_group" "runner" {
  name              = "/banking/banking-dev/codebuild"
  retention_in_days = 365
  kms_key_id        = data.terraform_remote_state.foundation.outputs.kms_key_arn
  tags              = merge(local.tags, { Name = "${local.name}-logs" })
}

# The webhook accepts queued jobs only from the exact repository and named
# deployment workflows. CodeBuild starts one ephemeral container per job.
resource "aws_codebuild_project" "runner" {
  name               = local.name
  description        = "Ephemeral private-VPC GitHub Actions runner for Banking EKS releases"
  service_role       = aws_iam_role.runner.arn
  build_timeout      = 90
  queued_timeout     = 30
  project_visibility = "PRIVATE"
  source {
    type            = "GITHUB"
    location        = "https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS.git"
    git_clone_depth = 1
    auth {
      type     = "CODECONNECTIONS"
      resource = var.github_connection_arn
    }
  }
  artifacts { type = "NO_ARTIFACTS" }
  environment {
    type            = "LINUX_CONTAINER"
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    privileged_mode = false # Hosted CI performs Docker/Trivy before this private job.
  }
  vpc_config {
    vpc_id  = data.terraform_remote_state.platform.outputs.vpc_id
    subnets = data.terraform_remote_state.platform.outputs.application_subnet_ids
    # The database admits the cluster SG. The temporary runner also needs it
    # for TLS migrations; its own SG remains the exact EKS API ingress source.
    security_group_ids = [aws_security_group.runner.id, data.terraform_remote_state.platform.outputs.cluster_security_group_id]
  }
  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.runner.name
      status     = "ENABLED"
    }
  }
  tags       = merge(local.tags, { Name = local.name })
  depends_on = [aws_iam_role_policy.runner, aws_vpc_security_group_ingress_rule.eks_api]
}

resource "aws_codebuild_webhook" "runner" {
  project_name = aws_codebuild_project.runner.name
  build_type   = "BUILD"
  filter_group {
    filter {
      type    = "EVENT"
      pattern = "WORKFLOW_JOB_QUEUED"
    }
    filter {
      type    = "WORKFLOW_NAME"
      pattern = "^(App CD|App Rollback|Infra CI/CD|Banking Kubernetes bootstrap|Terraform Destroy)$"
    }
  }
}

output "project_name" { value = aws_codebuild_project.runner.name }
output "project_arn" { value = aws_codebuild_project.runner.arn }
output "security_group_id" { value = aws_security_group.runner.id }
output "webhook_url" { value = aws_codebuild_webhook.runner.url }
output "runner_label_prefix" { value = "codebuild-${local.name}" }
output "state_key" { value = "banking-release-platform/shared/runner/terraform.tfstate" }
