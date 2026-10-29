# What a bundle cannot create: the IAM role Unity Catalog assumes to read your buckets, and the
# storage credential that wraps it. The bundle (prod target) creates the external locations on top.

locals {
  role_name = "${var.name_prefix}-uc-access"
  buckets   = [var.dms_bucket, var.documents_bucket]
}

# Trust policy for the Unity Catalog master role, plus the self-assume statement UC requires
data "databricks_aws_unity_catalog_assume_role_policy" "this" {
  aws_account_id = var.aws_account_id
  role_name      = local.role_name
  external_id    = databricks_storage_credential.this.aws_iam_role[0].external_id
}

# Read access to both buckets (the pipelines never write to them)
data "aws_iam_policy_document" "read_buckets" {
  statement {
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket", "s3:GetBucketLocation"]
    resources = flatten([for b in local.buckets : ["arn:aws:s3:::${b}", "arn:aws:s3:::${b}/*"]])
  }
  # Auto Loader file events (recommended for near real time): S3 notifications, SNS and SQS
  statement {
    actions = ["s3:GetBucketNotification", "s3:PutBucketNotification", "sns:ListSubscriptionsByTopic",
      "sns:GetTopicAttributes", "sns:SetTopicAttributes", "sns:CreateTopic", "sns:TagResource",
      "sns:Publish", "sns:Subscribe", "sqs:CreateQueue", "sqs:DeleteMessage", "sqs:ReceiveMessage",
      "sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes",
    "sqs:TagQueue", "sqs:ChangeMessageVisibility", "sqs:PurgeQueue"]
    resources = flatten([
      [for b in local.buckets : "arn:aws:s3:::${b}"],
      ["arn:aws:sqs:*:*:csms-*", "arn:aws:sns:*:*:csms-*"],
    ])
  }
  statement {
    actions   = ["sqs:ListQueues", "sqs:ListQueueTags", "sns:ListTopics"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "uc" {
  name               = local.role_name
  assume_role_policy = data.databricks_aws_unity_catalog_assume_role_policy.this.json
  description        = "Unity Catalog read access to the DMS and documents buckets"
}

resource "aws_iam_role_policy" "read_buckets" {
  name   = "read-buckets"
  role   = aws_iam_role.uc.id
  policy = data.aws_iam_policy_document.read_buckets.json
}

resource "databricks_storage_credential" "this" {
  name    = "${var.name_prefix}_s3_read"
  comment = "Reads the DMS and documents buckets"
  aws_iam_role {
    role_arn = "arn:aws:iam::${var.aws_account_id}:role/${local.role_name}"
  }
  read_only = true
}
