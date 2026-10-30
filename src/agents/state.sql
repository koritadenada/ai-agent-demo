-- What the app writes. Nothing is written without the analyst confirming it in the app.
CREATE TABLE IF NOT EXISTS {catalog}.{app_schema}.analyst_decisions (
  decision_id STRING NOT NULL,
  evaluation_id BIGINT NOT NULL COMMENT 'The final DA (FDA) decided on',
  port_call_id BIGINT,
  decision STRING NOT NULL COMMENT 'accept, dispute or hold',
  note STRING,
  lines_flagged INT COMMENT 'Lines the rules flagged when the decision was taken',
  decided_by STRING NOT NULL,
  decided_at TIMESTAMP NOT NULL
) COMMENT 'Accept, dispute or hold decisions on final DAs, taken in the DA review screen'
TBLPROPERTIES ('delta.enableRowTracking' = 'true');

CREATE TABLE IF NOT EXISTS {catalog}.{app_schema}.negotiation_drafts (
  draft_id STRING NOT NULL,
  proforma_id BIGINT NOT NULL COMMENT 'The PDA quote the email negotiates',
  port_call_id BIGINT,
  agent_name STRING COMMENT 'The port agent the email is addressed to',
  subject STRING,
  body STRING,
  lines STRING COMMENT 'JSON: the quote lines negotiated, quoted and target amounts and the evidence cited',
  unverified_numbers STRING COMMENT 'JSON: amounts in the email that were not found in the data the agent read',
  prompt_version STRING,
  model STRING,
  created_by STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
) COMMENT 'Negotiation emails drafted by the AI Negotiator and saved by an analyst'
TBLPROPERTIES ('delta.enableRowTracking' = 'true');

CREATE TABLE IF NOT EXISTS {catalog}.{app_schema}.agent_registry (
  agent STRING NOT NULL,
  endpoint_name STRING,
  resource_id STRING,
  updated_at TIMESTAMP
) COMMENT 'Where the app finds each agent (supervisor endpoint, Genie space ids); written by the setup job';
