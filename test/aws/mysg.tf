resource "aws_security_group" "mysg" {
  count       = var.mycount
  description = "SG-inbound"
  vpc_id      = aws_vpc.VPC[count.index].id
}
