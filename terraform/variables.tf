variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-west-3" # Paris
}

variable "project_name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "ferrari-f1"
}

variable "instance_type" {
  description = "EC2 instance type for the application/monitoring server."
  type        = string
  default     = "t3.large"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDRs for the two public subnets (RDS needs two AZs)."
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to reach SSH and the dashboards (use YOUR_IP/32)."
  type        = string
}

variable "key_pair_name" {
  description = "Name of an existing EC2 key pair for SSH access."
  type        = string
}

variable "app_repo_url" {
  description = "Git URL of the F1 pipeline repository the server clones and runs."
  type        = string
  default     = "https://github.com/enzoberreur/f1-streaming-pipeline.git"
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "ferrari_f1"
}

variable "db_username" {
  description = "PostgreSQL master username."
  type        = string
  default     = "ferrari"
}

variable "db_password" {
  description = "PostgreSQL master password (provide via TF_VAR_db_password or tfvars)."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}
