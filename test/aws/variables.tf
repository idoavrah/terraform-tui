variable "mycount" {
  default = 1
}

variable "aws_vpc" {
  type    = list(any)
  default = ["vpc-10-1", "vpc-10-2"]
}

variable "aws_cidr" {
  default = {
    "vpc-10-1"       = "10.1.0.0/16"
    "vpc-devt-proja" = "10.3.0.0/16"
    "vpc-10-2"       = "10.2.0.0/16"
    "vpc-devt-projx" = "10.4.0.0/16"
  }
}
