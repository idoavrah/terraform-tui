provider "random" {
}

resource "random_integer" "random_number" {
  count = 5
  min = 1
  max = 100
}

variable "input_number" {
  description = "Input number for the module"
}
