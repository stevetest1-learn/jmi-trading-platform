resource "aws_iam_role" "eod_scheduler" {
  name = "${var.project_name}-eod-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy" "eod_scheduler_run_task" {
  name = "${var.project_name}-eod-scheduler-run-task"
  role = aws_iam_role.eod_scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = replace(aws_ecs_task_definition.eod_settlement.arn, "/:\\d+$/", ":*")
        Condition = {
          ArnLike = { "ecs:cluster" = aws_ecs_cluster.main.arn }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.ecs_execution.arn, aws_iam_role.ecs_task.arn]
      },
    ]
  })
}

# Runs the same image as the backend service with its command overridden --
# see ecs.tf's eod_settlement task def and backend/app/settlement/eod.py.
resource "aws_scheduler_schedule" "eod_settlement" {
  name       = "${var.project_name}-eod-settlement"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = var.eod_settlement_schedule

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.eod_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.eod_settlement.arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
        security_groups  = [aws_security_group.backend.id]
        assign_public_ip = true
      }
    }
  }
}
