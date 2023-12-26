terraform {
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "3.5.1"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.4.1"
    }
  }
}

provider "random" {
}

module "mercury" {
  source       = "./module"
  input_number = random_integer.random_number.result
}

module "dots" {
  for_each     = toset(["string.with.dots", "another.string.with.dots"])
  source       = "./module"
  input_number = random_integer.random_number.result
}

module "colons" {
  for_each     = toset(["string:with:colons", "another:string:with:colons"])
  source       = "./module"
  input_number = random_integer.random_number.result
}

resource "random_integer" "random_number" {
  min = 1
  max = 100
}

data "local_file" "saturn" {
  count    = 3
  filename = "${path.module}/1.txt"
}

#module "aws" {
#  source = "./aws"
#}
