resource "random_integer" "jupiter" {
  count = 5
  min   = 1
  max   = 100
}

variable "input_number" {
  description = "Input number for the module"
}


module "venus" {
  source       = "../module2"
  count        = 2
  input_number = var.input_number
}

data "local_file" "pluto" {
  count    = 2
  filename = "${path.module}/1.txt"
}
