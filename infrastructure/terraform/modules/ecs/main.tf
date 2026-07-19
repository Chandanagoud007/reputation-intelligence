# ─── Variables ────────────────────────────────────────────────────────────────
variable "environment" {}
variable "vpc_id" {}
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "aws_region" {}
variable "db_url" { sensitive = true }
variable "redis_url" {}
variable "target_group_arn" { default = "" }

# ─── ECS Cluster ──────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "reputation-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "reputation-${var.environment}-cluster"
  }
}

# ─── IAM Role for ECS Task Execution ─────────────────────────────────────────
resource "aws_iam_role" "ecs_task_execution" {
  name = "reputation-${var.environment}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_ecr_pull" {
  name = "reputation-${var.environment}-ecr-pull"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ]
      Resource = "*"
    }]
  })
}

# ─── Security Group for ECS ───────────────────────────────────────────────────
resource "aws_security_group" "ecs" {
  name        = "reputation-${var.environment}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "reputation-${var.environment}-ecs-sg"
  }
}

# ─── CloudWatch Log Group ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/reputation-${var.environment}-backend"
  retention_in_days = 30
}

# ─── ECS Task Definition ──────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "backend" {
  family                   = "reputation-${var.environment}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name  = "backend"
    image = "684389449202.dkr.ecr.us-east-1.amazonaws.com/reputation-intelligence-staging"
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [
      { name = "APP_ENV",                value = var.environment },
      { name = "DEBUG",                  value = "false" },
      { name = "SECRET_KEY",             value = var.secret_key },
      { name = "JWT_SECRET_KEY",         value = var.jwt_secret_key },
      { name = "DATABASE_URL",           value = var.db_url },
      { name = "POSTGRES_HOST",          value = var.postgres_host },
      { name = "POSTGRES_PORT",          value = "5432" },
      { name = "POSTGRES_USER",          value = var.postgres_user },
      { name = "POSTGRES_PASSWORD",      value = var.postgres_password },
      { name = "POSTGRES_DB",            value = var.postgres_db },
      { name = "MONGO_URI",              value = var.mongo_uri },
      { name = "MONGO_DB",               value = "reputation_reviews" },
      { name = "REDIS_URL",              value = var.redis_url },
      { name = "RABBITMQ_URL",           value = var.rabbitmq_url },
      { name = "AWS_REGION",             value = var.aws_region },
      { name = "AWS_ACCESS_KEY_ID",      value = var.app_aws_access_key_id },
      { name = "AWS_SECRET_ACCESS_KEY",  value = var.app_aws_secret_access_key },
      { name = "AWS_S3_BUCKET",          value = var.s3_bucket },
      { name = "AWS_SES_SENDER_EMAIL",   value = var.ses_sender_email },
      { name = "ALLOWED_HOSTS",          value = var.alb_dns_name },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "backend"
      }
    }
  }])
}

# ─── ECS Service ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "backend" {
  name            = "reputation-${var.environment}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn != "" ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = "backend"
      container_port   = 8000
    }
  }

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "cluster_name" {
  value = aws_ecs_cluster.main.name
}
output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

variable "secret_key" { sensitive = true }
variable "jwt_secret_key" { sensitive = true }
variable "postgres_host" {}
variable "postgres_user" {}
variable "postgres_password" { sensitive = true }
variable "postgres_db" {}
variable "mongo_uri" { sensitive = true }
variable "rabbitmq_url" { default = "amqp://guest:guest@localhost:5672/" }
variable "app_aws_access_key_id" { sensitive = true }
variable "app_aws_secret_access_key" { sensitive = true }
variable "s3_bucket" {}
variable "ses_sender_email" { default = "" }
variable "alb_dns_name" { default = "" }