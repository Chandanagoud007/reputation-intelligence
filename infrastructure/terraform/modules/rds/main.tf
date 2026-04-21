# ─── Security Group ───────────────────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name        = "reputation-${var.environment}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "reputation-${var.environment}-rds-sg"
  }
}

# ─── Subnet Group ─────────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "reputation-${var.environment}-db-subnet"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "reputation-${var.environment}-db-subnet"
  }
}

# ─── RDS Instance ─────────────────────────────────────────────────────────────
resource "aws_db_instance" "main" {
  identifier        = "reputation-${var.environment}-postgres"
  engine            = "postgres"
  instance_class    = var.instance_class
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 0
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  skip_final_snapshot     = true
  deletion_protection     = var.environment == "production"

  tags = {
    Name = "reputation-${var.environment}-postgres"
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "db_url" {
  value     = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.endpoint}/${var.db_name}"
  sensitive = true
}

output "db_endpoint" {
  value = aws_db_instance.main.endpoint
}

variable "environment" {}
variable "vpc_id" {}
variable "subnet_ids" { type = list(string) }
variable "db_name" {}
variable "db_username" {}
variable "db_password" { sensitive = true }
variable "instance_class" {}
