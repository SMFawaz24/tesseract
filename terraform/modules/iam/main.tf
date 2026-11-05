# Role for Standard AWS Accounts (Least-Privilege)
resource "aws_iam_role" "node_role" {
  count = var.use_aws_academy_lab_profile ? 0 : 1
  name  = "k8s-node-least-privilege-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "cw_put_policy" {
  count       = var.use_aws_academy_lab_profile ? 0 : 1
  name        = "k8s-cw-put-metric-policy"
  description = "Allows pushing custom metrics to AutoScaler/App namespace only"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "cloudwatch:PutMetricData"
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "AutoScaler/App"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${var.s3_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeSpotPriceHistory", "ec2:DescribeInstances"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "node_attach" {
  count      = var.use_aws_academy_lab_profile ? 0 : 1
  role       = aws_iam_role.node_role[0].name
  policy_arn = aws_iam_policy.cw_put_policy[0].arn
}

resource "aws_iam_instance_profile" "standard_profile" {
  count = var.use_aws_academy_lab_profile ? 0 : 1
  name  = "k8s-node-instance-profile"
  role  = aws_iam_role.node_role[0].name
}

