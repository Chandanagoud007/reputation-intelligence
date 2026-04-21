# ─── Variables ────────────────────────────────────────────────────────────────
variable "environment" {}
variable "vpc_id" {}
variable "subnet_ids" { type = list(string) }
variable "node_type" {}

# ─── Security Group ───────────────────────────────────────────────────────────
resource "aws_security_group" "redis" {
  name        = "reputation-${var.environment}-redis-sg"
  description = "Security group for ElastiCache Redis"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
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
    Name = "reputation-${var.environment}-redis-sg"
  }
}

# ─── Subnet Group ─────────────────────────────────────────────────────────────
resource "aws_elasticache_subnet_group" "main" {
  name       = "reputation-${var.environment}-redis-subnet"
  subnet_ids = var.subnet_ids
}

# ─── ElastiCache Cluster ──────────────────────────────────────────────────────
resource "aws_elasticache_cluster" "main" {
  cluster_id           = "reputation-${var.environment}-redis"
  engine               = "redis"
  node_type            = var.node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = {
    Name = "reputation-${var.environment}-redis"
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "redis_url" {
  value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379/0"
}