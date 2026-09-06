variable "input_number" {
  description = "Input number for the module"
  type        = number
}

variable "prefix" {
  description = "Unique prefix so each module instance owns distinct files."
  type        = string
}

resource "random_integer" "jupiter" {
  count = 5
  min   = 1
  max   = 100
}

resource "random_password" "password" {
  length  = 16
  special = true
}

data "local_file" "pluto" {
  count    = 2
  filename = "${path.module}/seed.txt"
}

module "venus" {
  source       = "../beta"
  count        = 2
  input_number = var.input_number
  prefix       = "${var.prefix}-venus${count.index}"
}
