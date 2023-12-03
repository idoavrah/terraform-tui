resource "random_integer" "random_number" {
  count = 5
  min   = 1
  max   = 100
}

variable "input_number" {
  description = "Input number for the module"
}


module "module2" {
  source       = "../module2"
  count        = 5
  input_number = var.input_number
}

data "local_file" "foo" {
  count    = 4
  filename = "${path.module}/1.txt"
}
