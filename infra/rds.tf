# Postgres holds the matching engine's durable state: accounts, orders,
# trades, positions, daily settlements. The in-memory order book is
# rehydrated from here on every backend restart (see backend/app/engine/engine.py
# bootstrap()).
resource "aws_db_instance" "main" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"

  db_name  = var.db_name
  username = var.db_username
  # RDS generates and manages the master password in Secrets Manager --
  # Terraform never sees or stores the plaintext.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false # demo: single-AZ halves the cost, no HA

  skip_final_snapshot = true
  deletion_protection = false

  tags = local.common_tags
}
