terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Store state in S3 (uncomment after creating the bucket manually)
  # backend "s3" {
  #   bucket = "reputation-intelligence-tfstate"
  #   key    = "infrastructure/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ReputationIntelligence"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ─── VPC ──────────────────────────────────────────────────────────────────────
module "vpc" {
  source = "./modules/vpc"

  environment         = var.environment
  vpc_cidr            = var.vpc_cidr
  availability_zones  = var.availability_zones
  public_subnet_cidrs = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

# ─── RDS (PostgreSQL) ─────────────────────────────────────────────────────────
module "rds" {
  source = "./modules/rds"

  environment     = var.environment
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnet_ids
  db_name         = var.db_name
  db_username     = var.db_username
  db_password     = var.db_password
  instance_class  = var.rds_instance_class
}

# ─── ElastiCache (Redis) ──────────────────────────────────────────────────────
module "elasticache" {
  source = "./modules/elasticache"

  environment = var.environment
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  node_type   = var.redis_node_type
}

# ─── ECS Cluster ──────────────────────────────────────────────────────────────
module "ecs" {
  source             = "./modules/ecs"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  aws_region         = var.aws_region
  target_group_arn   = module.alb.target_group_arn

  # App config
  secret_key         = var.secret_key
  jwt_secret_key     = var.jwt_secret_key
  db_url             = module.rds.db_url
  postgres_host      = var.postgres_host
  postgres_user      = var.db_username
  postgres_password  = var.db_password
  postgres_db        = var.db_name
  mongo_uri          = var.mongo_uri
  rabbitmq_url       = var.rabbitmq_url
  redis_url          = module.elasticache.redis_url
  app_aws_access_key_id     = var.app_aws_access_key_id
  app_aws_secret_access_key = var.app_aws_secret_access_key
  s3_bucket          = aws_s3_bucket.assets.bucket
  ses_sender_email   = var.ses_sender_email
  alb_dns_name       = module.alb.alb_dns_name
}# ─── S3 Bucket ────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "assets" {
  bucket = "reputation-intelligence-assets-${var.environment}"
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ─── ALB ──────────────────────────────────────────────────────────────────────
module "alb" {
  source                = "./modules/alb"
  environment           = var.environment
  vpc_id                = module.vpc.vpc_id
  public_subnet_ids     = module.vpc.public_subnet_ids
  ecs_security_group_id = module.ecs.ecs_security_group_id
}
