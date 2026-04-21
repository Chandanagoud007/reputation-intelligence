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
  source = "./modules/ecs"

  environment       = var.environment
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  aws_region        = var.aws_region
  db_url            = module.rds.db_url
  redis_url         = module.elasticache.redis_url
}

# ─── S3 Bucket ────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "assets" {
  bucket = "reputation-intelligence-assets-${var.environment}"
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = "Enabled"
  }
}
