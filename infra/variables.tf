variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix used for all created resources"
  type        = string
  default     = "jmi-crypto"
}

variable "environment" {
  description = "Deployment environment tag (dev, staging, prod, ...)"
  type        = string
  default     = "dev"
}

variable "backend_image_tag" {
  description = "Docker image tag for the backend service, pushed to the ECR repo this stack creates"
  type        = string
  default     = "latest"
}

variable "backend_cpu" {
  description = "Fargate task CPU units for the backend service"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Fargate task memory (MB) for the backend service"
  type        = number
  default     = 1024
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "jmi_trading"
}

variable "db_username" {
  description = "Postgres master username"
  type        = string
  default     = "jmi"
}

variable "eod_settlement_schedule" {
  description = "Cron expression (UTC) for the daily settlement job"
  type        = string
  default     = "cron(0 21 * * ? *)"
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the backend service"
  type        = number
  default     = 14
}

variable "deploy_fix_gateway" {
  description = "Whether to deploy the FIX gateway template as its own ECS service"
  type        = bool
  default     = false
}

variable "fix_gateway_image_tag" {
  description = "Docker image tag for the FIX gateway (only used if deploy_fix_gateway = true)"
  type        = string
  default     = "latest"
}

variable "fix_gateway_allowed_cidrs" {
  description = "CIDR blocks allowed to reach the FIX gateway's TCP port -- FIX has no transport-layer auth, keep this tight"
  type        = list(string)
  default     = []
}
