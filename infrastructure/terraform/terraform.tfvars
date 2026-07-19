# terraform.tfvars  ← NEVER commit this file

# terraform.tfvars ← NEVER commit this file

aws_region  = "us-east-1"
environment = "staging"

vpc_cidr             = "10.0.0.0/16"
availability_zones   = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

db_name            = "reputation_db"
db_username        = "repuser"
db_password        = "Cheekala070305"  # ← set a real password here
rds_instance_class = "db.t3.micro"

redis_node_type = "cache.t3.micro"

secret_key     = "f1b3ef9c9fcb342f976e432d91e3ef45c3483dea12ccaf58ea98f56c7c835347"
jwt_secret_key = "9c7f1c7f08bf9dc07b1df528534ed816f8b72e24fda359bb8fbae253e0fe10ab"

postgres_host = "reputation-staging-postgres.c85ogm40ul3d.us-east-1.rds.amazonaws.com"

mongo_uri    = "mongodb+srv://repuser:Chandana%403065@repuser.nyd3lhl.mongodb.net/reputation_reviews?retryWrites=true&w=majority&appName=repuser"
rabbitmq_url = "amqp://repuser:Cheekala070305@localhost:5672/reputation"

app_aws_access_key_id     = "AKIAZ6WGKHXZDHYYXDOG"
app_aws_secret_access_key = "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"
ses_sender_email          = "chandanagoud007@gmail.com"