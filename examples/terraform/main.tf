# Example project used by tftui's integration tests and for manual exploration.
#
# It deliberately exercises the awkward corners of terraform addressing:
#   * nested modules (3 levels deep)
#   * for_each keys containing dots, colons and hash signs
#   * count-indexed resources and data sources
#   * sensitive attributes
# All providers are hermetic (random / local / time) so `terraform apply`
# creates nothing outside this directory.

terraform {
  required_version = ">= 1.5"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "3.6.3"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.5.2"
    }
    time = {
      source  = "hashicorp/time"
      version = "0.12.1"
    }
  }
}

variable "something" {
  description = "Proves that -var-file handling works end to end."
  type        = string
}

resource "random_integer" "random_number" {
  min = 1
  max = 100
}

resource "time_static" "example" {}

resource "random_password" "password" {
  length  = 16
  special = true
}

data "local_file" "saturn" {
  count    = 3
  filename = "${path.module}/seed.txt"
}

module "mercury" {
  source       = "./modules/alpha"
  input_number = random_integer.random_number.result
  prefix       = "mercury"
}

module "dots" {
  for_each     = toset(["string.with.dots", "another.string.with.dots"])
  source       = "./modules/alpha"
  input_number = random_integer.random_number.result
  prefix       = "dots-${index(tolist(["string.with.dots", "another.string.with.dots"]), each.key)}"
}

module "colons" {
  for_each     = toset(["string:with:colons", "another:string:with:colons"])
  source       = "./modules/alpha"
  input_number = random_integer.random_number.result
  prefix       = "colons-${index(tolist(["string:with:colons", "another:string:with:colons"]), each.key)}"
}

output "greeting" {
  value = "hello ${var.something}"
}
