mock_provider "aws" {}
variables {
  bucket_name = "banking-offline-test-fixture"
}
run "security_controls" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls && aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket_public_access_block.state.ignore_public_acls && aws_s3_bucket_public_access_block.state.restrict_public_buckets
    error_message = "All four public access blocks must be enabled."
  }
  assert {
    condition     = aws_s3_bucket_ownership_controls.state.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled."
  }
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning must be enabled."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "State bucket must use S3-managed encryption."
  }
  assert {
    condition     = aws_s3_bucket.state.force_destroy == false
    error_message = "Force-destroy must remain disabled."
  }
}
run "retention_controls" {
  command = plan
  assert {
    condition     = one(aws_s3_bucket_lifecycle_configuration.state.rule).noncurrent_version_expiration[0].noncurrent_days == 90
    error_message = "Old versions have the documented retention."
  }
  assert {
    condition     = length(one(aws_s3_bucket_lifecycle_configuration.state.rule).expiration) == 0
    error_message = "Current state must never expire."
  }
}
run "invalid_bucket_name" {
  command = plan
  variables { bucket_name = "Invalid_BUCKET" }
  expect_failures = [var.bucket_name]
}
