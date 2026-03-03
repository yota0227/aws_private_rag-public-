# Backend Configuration for Kiro Subscription
# Uses local backend for development
# For production, use S3 backend with proper credentials

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
