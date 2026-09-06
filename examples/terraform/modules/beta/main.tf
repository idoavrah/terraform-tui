variable "input_number" {
  description = "Input number for the module"
  type        = number
}

variable "prefix" {
  description = "Unique prefix so each module instance owns distinct files."
  type        = string
}

resource "local_file" "foo" {
  for_each = toset(["#1", "#2", "#3"])
  content  = "${each.value}\n"
  filename = "${path.root}/generated/${var.prefix}_${each.value}.txt"
}

module "uranus" {
  source       = "../gamma"
  input_number = var.input_number
}
