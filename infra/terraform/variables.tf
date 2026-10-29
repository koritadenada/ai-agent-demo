variable "aws_region" {
  type        = string
  description = "Region of the two S3 buckets"
}

variable "aws_account_id" {
  type        = string
  description = "AWS account that owns the buckets and the IAM role"
}

variable "databricks_host" {
  type        = string
  description = "Workspace URL, for example https://dbc-xxxx.cloud.databricks.com"
}

variable "dms_bucket" {
  type        = string
  description = "Existing bucket that AWS DMS writes to (name only)"
}

variable "documents_bucket" {
  type        = string
  description = "Existing bucket that holds the PDF documents (name only)"
}

variable "name_prefix" {
  type        = string
  default     = "portcall"
  description = "Prefix for the IAM role and the storage credential"
}
