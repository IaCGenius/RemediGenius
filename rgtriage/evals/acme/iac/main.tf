resource "aws_s3_bucket" "payments_exports" {
  bucket = "acme-payments-exports"
  tags = {
    app = "payments"
    env = "prod"
  }
}

resource "aws_security_group" "bastion" {
  name = "bastion"
  tags = { env = "prod" }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
