provider "random" {
}

resource "random_integer" "random_number" {
  min = 1
  max = 100
}

variable "input_number" {
  description = "Input number for the module"
}

output "output_number" {
  value = random_integer.random_number.result + var.input_number
}

