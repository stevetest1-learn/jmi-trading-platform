resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# ---------- IAM ----------

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-ecs-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The execution role needs read access to the specific secrets referenced
# in the task definition's `secrets` block below (JWT signing secret + the
# RDS-managed master password), on top of the managed ECR/Logs policy above.
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.project_name}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.jwt_secret.arn,
        aws_db_instance.main.master_user_secret[0].secret_arn,
      ]
    }]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

# ---------- Backend service (the matching engine) ----------

locals {
  backend_env = [
    { name = "DATABASE_HOST", value = aws_db_instance.main.address },
    { name = "DATABASE_PORT", value = tostring(aws_db_instance.main.port) },
    { name = "DATABASE_NAME", value = var.db_name },
    { name = "DATABASE_USER", value = var.db_username },
    { name = "CORS_ORIGINS", value = jsonencode(["*"]) },
  ]

  backend_secrets = [
    { name = "JWT_SECRET", valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
    { name = "DATABASE_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" },
  ]

  backend_image = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name         = "backend"
      image        = local.backend_image
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = local.backend_env
      secrets      = local.backend_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])

  tags = local.common_tags
}

# IMPORTANT: desired_count is pinned to 1. The matching engine keeps its
# order book in memory and is single-writer by design (one asyncio.Lock
# guards every submit/cancel -- see backend/app/engine/engine.py). Running
# more than one task would give each replica its own, inconsistent, book.
# This is the right call for a demo/sandbox exchange; scaling beyond one
# writer would need a real redesign (e.g. a single-writer process behind a
# queue), not just bumping this number.
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]

  tags = local.common_tags
}

# ---------- EOD settlement task (run on a schedule, see eventbridge.tf) ----------

resource "aws_ecs_task_definition" "eod_settlement" {
  family                   = "${var.project_name}-eod-settlement"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name        = "eod-settlement"
      image       = local.backend_image # same image as the service, different command
      essential   = true
      command     = ["python", "-m", "scripts.run_eod_settlement"]
      environment = local.backend_env
      secrets     = local.backend_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "eod-settlement"
        }
      }
    }
  ])

  tags = local.common_tags
}

# ---------- FIX gateway (optional, off by default) ----------

resource "aws_cloudwatch_log_group" "fix_gateway" {
  count             = var.deploy_fix_gateway ? 1 : 0
  name              = "/ecs/${var.project_name}-fix-gateway"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_ecs_task_definition" "fix_gateway" {
  count                    = var.deploy_fix_gateway ? 1 : 0
  family                   = "${var.project_name}-fix-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name         = "fix-gateway"
      image        = "${aws_ecr_repository.fix_gateway[0].repository_url}:${var.fix_gateway_image_tag}"
      essential    = true
      portMappings = [{ containerPort = 9878, protocol = "tcp" }]
      environment = [
        { name = "BACKEND_BASE_URL", value = "http://${aws_lb.backend.dns_name}" },
        { name = "BACKEND_WS_URL", value = "ws://${aws_lb.backend.dns_name}/ws" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.fix_gateway[0].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "fix-gateway"
        }
      }
    }
  ])

  tags = local.common_tags
}

# Deployed as a standalone service with a public IP + a locked-down security
# group (fix_gateway_allowed_cidrs) rather than a Network Load Balancer --
# an NLB is another always-on cost line that isn't justified for what's
# explicitly a template/demo integration point, not a production endpoint.
resource "aws_ecs_service" "fix_gateway" {
  count           = var.deploy_fix_gateway ? 1 : 0
  name            = "${var.project_name}-fix-gateway"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.fix_gateway[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.fix_gateway[0].id]
    assign_public_ip = true
  }

  tags = local.common_tags
}
