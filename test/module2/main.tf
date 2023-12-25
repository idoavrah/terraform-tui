resource "random_integer" "earth" {
  count = 2
  min   = 1
  max   = 100
}

variable "input_number" {
  description = "Input number for the module"
}


module "uranus" {
  source       = "../module3"
  input_number = var.input_number
}
