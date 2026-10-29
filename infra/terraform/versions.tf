terraform {
  required_version = ">= 1.6"
  required_providers {
    aws        = { source = "hashicorp/aws", version = ">= 5.0" }
    databricks = { source = "databricks/databricks", version = ">= 1.80" }
  }
}

provider "aws" {
  region = var.aws_region
}

# Workspace-level provider: authenticate with a CLI profile (DATABRICKS_CONFIG_PROFILE) or host + token
provider "databricks" {
  host = var.databricks_host
}
