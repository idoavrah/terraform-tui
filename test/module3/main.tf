resource "random_integer" "random_number" {
  for_each = toset(["e.f", "g.h"])
  min = 1
  max = 100
}

variable "input_number" {
  description = "Input number for the module"
}
