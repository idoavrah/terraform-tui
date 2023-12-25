terraform {
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "3.5.1"
    }
  }
}

provider "random" {
}

module "mercury" {
  source       = "./module"
  input_number = random_integer.random_number.result
}

module "dotted" {
  for_each     = toset(["a.b", "c.d"])
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
