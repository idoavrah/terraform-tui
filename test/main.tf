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

module "random_module" {
  source       = "./module"
  input_number = random_integer.random_number.result
}

resource "random_integer" "random_number" {
  min = 1
  max = 100
}

module "aws" {
  source = "./aws"
}
