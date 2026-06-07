provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "ferrari-f1-iot"
      ManagedBy = "terraform"
      Bloc      = "automation-deployment"
    }
  }
}
