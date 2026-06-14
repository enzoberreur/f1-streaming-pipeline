output "state_bucket_name" {
  description = "S3 bucket to reference in the backend \"s3\" block."
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "DynamoDB lock table to reference in the backend \"s3\" block."
  value       = aws_dynamodb_table.tf_locks.name
}
