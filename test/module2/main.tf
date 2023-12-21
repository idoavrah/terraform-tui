resource "random_integer" "random_number" {
  count = 2
  min = 1
  max = 100
}

variable "input_number" {
  description = "Input number for the module"
}


module "module3" {
  source = "../module3"
  count = 3
  input_number = var.input_number
}
