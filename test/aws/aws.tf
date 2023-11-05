terraform {
  required_version = "> 1.5.0"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      #  Fix version version of the AWS provider
      version = "= 5.3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "The name of the AWS Region"
  type        = string
  default     = "eu-west-1"
}
