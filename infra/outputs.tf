output "alb_dns_name" {
  description = "Backend API/WS base host. Frontend VITE_API_BASE_URL should be http://<this>"
  value       = aws_lb.backend.dns_name
}

output "ecr_backend_repository_url" {
  description = "Push the backend image here before the ECS service can start"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "db_endpoint" {
  description = "RDS Postgres endpoint (private -- reachable only from the backend security group)"
  value       = aws_db_instance.main.address
}

output "db_master_secret_arn" {
  description = "Secrets Manager ARN holding the RDS-generated master password"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "frontend_bucket_name" {
  description = "Upload the built frontend (frontend/dist) here"
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_domain_name" {
  description = "Public URL for the hosted frontend"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "Used for cache invalidation after deploying new frontend builds"
  value       = aws_cloudfront_distribution.frontend.id
}

output "fix_gateway_ecr_repository_url" {
  description = "Only set when deploy_fix_gateway = true"
  value       = try(aws_ecr_repository.fix_gateway[0].repository_url, null)
}
