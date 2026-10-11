terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
variable "name" { type = string }
resource "aws_ecr_repository" "service" {
  # checkov:skip=CKV_AWS_136:ECR uses AES256 at rest; customer KMS registry encryption is deferred to Phase 6.
  for_each             = toset(["account", "payment"])
  name                 = "${var.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name
  # Keep every tagged release for rollback; remove only untagged build debris.
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "Expire untagged images after seven days",
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 },
    action       = { type = "expire" }
  }] })
}
output "repositories" { value = { for name, repository in aws_ecr_repository.service : name => repository.repository_url } }
