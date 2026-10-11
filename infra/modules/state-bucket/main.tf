terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}

variable "bucket_name" {
  type        = string
  description = "Explicitly approved, globally unique dedicated banking state bucket."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name)) && !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.bucket_name)) && !strcontains(var.bucket_name, "..")
    error_message = "Use a valid 3–63 character S3 bucket name."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_s3_bucket" "state" {
  # checkov:skip=CKV_AWS_18:Dedicated state bucket logging destination awaits approved Phase 6 audit design.
  # checkov:skip=CKV_AWS_144:Single-region lab; cross-region replication requires a separate approved cost decision.
  # checkov:skip=CKV_AWS_145:Phase 2 uses S3-managed AES256 encryption; customer KMS keys await explicit approval.
  # checkov:skip=CKV2_AWS_62:Bucket event notifications are not required for Terraform locking; operations alerts belong to Phase 6.
  bucket        = var.bucket_name
  force_destroy = false
  tags          = var.tags
  lifecycle {
    prevent_destroy = true
  }
}
resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket     = aws_s3_bucket.state.id
  depends_on = [aws_s3_bucket_versioning.state]
  rule {
    id     = "retain-current-state-and-limit-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 90 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}
output "bucket_name" { value = aws_s3_bucket.state.bucket }
output "bucket_arn" { value = aws_s3_bucket.state.arn }
