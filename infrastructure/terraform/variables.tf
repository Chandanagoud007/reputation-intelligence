variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (staging or production)"
  type        = string
  default     = "staging"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "reputation_db"
}

variable "db_username" {
  description = "PostgreSQL username"
  type        = string
  default     = "repuser"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "secret_key" {
  description = "Django/FastAPI secret key"
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
}

variable "postgres_host" {
  description = "PostgreSQL host"
  type        = string
  default     = "reputation-staging-postgres.c85ogm40ul3d.us-east-1.rds.amazonaws.com"
}

variable "mongo_uri" {
  description = "MongoDB connection URI"
  type        = string
  sensitive   = true
}

variable "rabbitmq_url" {
  description = "RabbitMQ connection URL"
  type        = string
  default     = "amqp://guest:guest@localhost:5672/"
}

variable "app_aws_access_key_id" {
  description = "AWS access key for app use"
  type        = string
  sensitive   = true
}

variable "app_aws_secret_access_key" {
  description = "AWS secret key for app use"
  type        = string
  sensitive   = true
}

variable "ses_sender_email" {
  description = "SES sender email address"
  type        = string
  default     = ""
}