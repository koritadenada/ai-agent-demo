output "storage_credential_name" {
  value       = databricks_storage_credential.this.name
  description = "Pass to the bundle: --var storage_credential_name=<this>"
}

output "dms_bucket_url" {
  value = "s3://${var.dms_bucket}/"
}

output "documents_bucket_url" {
  value = "s3://${var.documents_bucket}/"
}
