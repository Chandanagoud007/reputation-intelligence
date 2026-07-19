# ─── Variables ────────────────────────────────────────────────────────────────
variable "environment" {}
variable "vpc_id" {}
variable "public_subnet_ids" { type = list(string) }
variable "ecs_security_group_id" {}

# ─── Security Group for ALB ───────────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name        = "reputation-${var.environment}-alb-sg"
  description = "Allow HTTP/HTTPS inbound"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
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
    Name = "reputation-${var.environment}-alb-sg"
  }
}

# ─── ALB ──────────────────────────────────────────────────────────────────────
resource "aws_lb" "main" {
  name               = "reputation-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = false

  tags = {
    Name = "reputation-${var.environment}-alb"
  }
}

# ─── Target Group ─────────────────────────────────────────────────────────────
resource "aws_lb_target_group" "backend" {
  name        = "reputation-${var.environment}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = {
    Name = "reputation-${var.environment}-backend-tg"
  }
}

# ─── Listener (HTTP) ──────────────────────────────────────────────────────────
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "target_group_arn" {
  value = aws_lb_target_group.backend.arn
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}