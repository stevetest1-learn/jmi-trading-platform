data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  az_a = data.aws_availability_zones.available.names[0]
  az_b = data.aws_availability_zones.available.names[1]
}
