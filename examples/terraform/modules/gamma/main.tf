variable "input_number" {
  description = "Input number for the module"
  type        = number
}

resource "random_integer" "mars" {
  for_each = toset(["e.f", "g.h"])
  min      = 1
  max      = 100
}
