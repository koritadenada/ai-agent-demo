# ai-agent-demo

Reference implementation for a port-call data platform that feeds AI agents on Databricks:
platform data replicated from PostgreSQL with AWS DMS and PDF documents, both landing in S3,
processed bronze to silver to gold, joined in one gold layer, and exposed through metric views
to Genie agents.

**Architecture:** [docs/architecture.html](https://koritadenada.github.io/ai-agent-demo/architecture.html)
(animated, click or use the arrow keys; `?mode=auto` loops it)

Work in progress: the pipelines, metric views and data generators are being added next.
