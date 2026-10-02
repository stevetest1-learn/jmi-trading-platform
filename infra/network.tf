resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.common_tags, { Name = "${var.project_name}-vpc" })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.common_tags, { Name = "${var.project_name}-igw" })
}

# Public subnets: ALB + Fargate backend tasks (assign_public_ip = true).
# Tasks reach ECR/Secrets Manager/the internet directly via the IGW -- no
# NAT gateway needed for this side either.
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.0.0/24"
  availability_zone       = local.az_a
  map_public_ip_on_launch = true
  tags                    = merge(local.common_tags, { Name = "${var.project_name}-public-a" })
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = local.az_b
  map_public_ip_on_launch = true
  tags                    = merge(local.common_tags, { Name = "${var.project_name}-public-b" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(local.common_tags, { Name = "${var.project_name}-public-rt" })
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# Private ISOLATED subnets: RDS only. No route to the internet gateway and
# deliberately no NAT gateway -- Postgres never needs outbound internet, and
# skipping NAT avoids its ~$32-38/month charge, the single biggest
# avoidable recurring cost in this stack.
resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.20.10.0/24"
  availability_zone = local.az_a
  tags              = merge(local.common_tags, { Name = "${var.project_name}-private-a" })
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.20.11.0/24"
  availability_zone = local.az_b
  tags              = merge(local.common_tags, { Name = "${var.project_name}-private-b" })
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  tags       = local.common_tags
}

# ---------- Security groups ----------

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Ingress from the internet on 80, open egress to the backend service"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "backend" {
  name        = "${var.project_name}-backend-sg"
  description = "Backend Fargate service: ingress from the ALB only, open egress (ECR/Secrets Manager/RDS)"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Postgres: ingress from the backend service only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.backend.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# Only created when deploy_fix_gateway = true. FIX has no transport-layer
# auth, so this must stay locked down to known counterparty IPs
# (fix_gateway_allowed_cidrs) rather than left open.
resource "aws_security_group" "fix_gateway" {
  count       = var.deploy_fix_gateway ? 1 : 0
  name        = "${var.project_name}-fix-gateway-sg"
  description = "FIX gateway: ingress restricted to fix_gateway_allowed_cidrs"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 9878
    to_port     = 9878
    protocol    = "tcp"
    cidr_blocks = var.fix_gateway_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}
