resource "local_file" "foo" {
  for_each = toset(["#1", "#2", "#3"])
  content  = "${each.value}\n"
  filename = "local_file${each.value}.txt"
}

variable "input_number" {
  description = "Input number for the module"
}

module "uranus" {
  source       = "../module3"
  input_number = var.input_number
}
