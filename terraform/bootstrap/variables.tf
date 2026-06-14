variable "aws_region" {
  description = "AWS region hosting the remote state."
  type        = string
  default     = "eu-west-3" # Paris
}

variable "state_bucket_name" {
  description = "Globally unique name of the S3 bucket holding the Terraform state."
  type        = string
  default     = "ferrari-f1-terraform-state"
}

variable "lock_table_name" {
  description = "Name of the DynamoDB table used for state locking."
  type        = string
  default     = "ferrari-f1-terraform-locks"
}
