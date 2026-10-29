"""Source tables replicated by AWS DMS from the DA database, and how each one is applied in silver.

One entry per table. Columns are whatever DMS writes; only keys and ordering matter here.
  keys          primary key, or the pair of foreign keys for link tables (they have no id)
  scd_type      2 keeps history (a change to a `track_history` column opens a new version), 1 keeps the latest row
  versioned     the table has a `version` column: changes are ordered by (version, commit time), as the source does
  assumed       lookup table referenced by the DA tables whose real columns are not confirmed yet (mock data only)

A table only gets bronze and silver when its DMS folder (or, with an existing bronze, its bronze table) exists,
so this list can describe the whole database while a smaller environment runs a subset.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceTable:
    name: str
    keys: tuple = ("id",)
    versioned: bool = False
    scd_type: int = 1
    track_history: tuple = ()
    assumed: bool = False
    comment: str = ""


V = dict(versioned=True)


def link(name, a, b, comment=""):
    return SourceTable(name, keys=(a, b), comment=comment)


TABLES = [
    # Core DA tables
    SourceTable("request_case", **V, comment="A buyer's request for quotations for one port call"),
    SourceTable("quotation", **V, comment="One supplier's quotation for a request case"),
    SourceTable("quotation_expense", **V, comment="Expense lines of a quotation"),
    SourceTable("port_call", **V, comment="One vessel calling at one port"),
    SourceTable("appointment", **V, scd_type=2, track_history=("state", "dashboard_status", "cancellation_reason"),
                comment="Appointment of the agent for a port call; state moves from in process to confirmed, completed or cancelled"),
    SourceTable("appointment_recipient", **V, comment="Supplier appointed (company_type AGENT or VENDOR)"),
    SourceTable("appointment_agent_recipient", comment="Agent subtype of appointment_recipient (same id)"),
    SourceTable("appointment_vendor_recipient", comment="Vendor subtype of appointment_recipient (same id)"),
    SourceTable("proforma", **V, scd_type=2, track_history=("state", "revision", "bank_account_id"),
                comment="Proforma disbursement account (PDA)"),
    SourceTable("proforma_expense", **V, comment="Quoted expense lines of a proforma"),
    SourceTable("evaluation", **V, scd_type=2, track_history=("state", "dashboard_status", "approval_date", "bank_account_id"),
                comment="Final disbursement account (FDA) evaluation of a proforma"),
    SourceTable("evaluation_verification", **V, comment="Sign-off of an evaluation by a buyer department"),
    SourceTable("expense_evaluation", **V, comment="Final expense lines; proforma_expense_id points to the quoted line"),
    SourceTable("expense_evaluation_verification", **V, comment="Analyst verification of a final line: discrepancy type and amount"),

    # Request / quotation family
    link("request_case_activities", "request_case_id", "activity_id"),
    link("request_case_attachments", "request_case_id", "file_item_id"),
    SourceTable("request_case_shared_email"),
    SourceTable("request_expense", **V),
    link("request_expense_husbandry_expense_parameter_option", "request_expense_id", "husbandry_expense_parameter_option_id"),
    SourceTable("request_for_quotation", **V, comment="Request for quotation sent to one supplier"),
    link("quotation_expense_husbandry_expense_parameter_option", "quotation_expense_id", "husbandry_expense_parameter_option_id"),

    # Port call family
    link("port_call_activities", "port_call_id", "activity_id"),
    SourceTable("port_call_comment_history"),
    link("port_call_request_case", "port_call_id", "request_case_id", "Request cases behind a port call"),

    # Appointment family
    SourceTable("appointment_charterers_account_claim", **V),
    SourceTable("appointment_charterers_account_claim_sent_email"),
    link("appointment_contact_buyer_profiles", "appointment_id", "buyer_profile_id"),
    link("appointment_contact_company_mail_groups", "appointment_id", "mail_group_id"),
    SourceTable("appointment_contact_email"),
    link("appointment_recipient_activities", "appointment_recipient_id", "activity_id"),

    # Proforma (PDA) family
    link("proforma_attachments", "file_item_id", "proforma_id", "Documents attached to a proforma (PDA and FDA packs)"),
    link("proforma_exported_pdf", "proforma_id", "file_item_id"),
    link("proforma_pre_invoice_attachments", "file_item_id", "proforma_id"),
    link("proforma_statement_of_facts", "file_item_id", "proforma_id", "Statements of facts of a proforma"),
    link("proforma_relations", "proforma_id", "related_proforma_id"),
    SourceTable("proforma_split_history"),
    link("proforma_expense_attachments", "file_item_id", "proforma_expense_id"),
    link("proforma_expense_husbandry_expense_parameter_option", "proforma_expense_id", "husbandry_expense_parameter_option_id"),

    # Evaluation (FDA) family
    SourceTable("evaluation_additional_integration_info"),
    SourceTable("evaluation_charterer_account_report"),
    SourceTable("evaluation_charterer_account_report_item"),
    link("evaluation_charterer_account_report_item_attachments", "file_item_id", "evaluation_charterer_account_report_item_id"),
    link("evaluation_charterer_account_report_merged_pdf", "evaluation_charterer_account_report_id", "file_item_id"),
    SourceTable("evaluation_charterers_account_claim", **V),
    SourceTable("evaluation_commissions"),
    SourceTable("evaluation_note", **V),
    link("evaluation_relations", "evaluation_id", "related_proforma_id"),
    SourceTable("evaluation_verification_flow_step"),
    SourceTable("evaluation_verification_signature"),
    link("evaluation_verification_signature_attachments", "file_item_id", "evaluation_verification_signature_id"),

    # Expense evaluation family
    SourceTable("expense_evaluation_action"),
    link("expense_evaluation_attachments", "file_item_id", "expense_evaluation_id", "Supporting documents of a final line"),
    link("expense_evaluation_husbandry_expense_parameter_option", "expense_evaluation_id", "husbandry_expense_parameter_option_id"),
    SourceTable("expense_evaluation_inspection", **V),
    SourceTable("expense_evaluation_inspection_calculation", **V),
    SourceTable("expense_evaluation_inspection_calculation_parameter_value"),
    SourceTable("expense_evaluation_inspection_verification", **V),
    link("expense_evaluation_inspection_verification_discrepancy_reason",
         "expense_evaluation_inspection_verification_id", "discrepancy_reason_id"),
    SourceTable("expense_evaluation_parameters_alter_history"),
    SourceTable("expense_evaluation_verification_flow"),
    SourceTable("expense_evaluation_verification_flow_step"),
    SourceTable("expense_evaluation_verification_signature"),
    link("expense_evaluation_verification_signature_attachments", "file_item_id", "expense_evaluation_verification_signature_id"),

    # Lookups outside the DA families: names and columns ASSUMED until confirmed
    SourceTable("vessel", **V, assumed=True, comment="ASSUMED: vessel master data"),
    SourceTable("port", **V, assumed=True, comment="ASSUMED: port master data with region"),
    SourceTable("buyer", **V, assumed=True, comment="ASSUMED: buyers (owners, operators, charterers)"),
    SourceTable("supplier", **V, assumed=True, comment="ASSUMED: suppliers (agents and vendors)"),
    SourceTable("expense_category", **V, assumed=True, comment="ASSUMED: expense taxonomy used by category_id"),
    SourceTable("bank_account", **V, scd_type=2, track_history=("iban", "account_number", "swift"), assumed=True,
                comment="ASSUMED: supplier bank accounts referenced by bank_account_id"),
    SourceTable("file_item", assumed=True, comment="ASSUMED: stored files with their S3 key"),
]

# Envelope written by DMS (TimestampColumnName, IncludeOpForFullLoad) and by the bronze ingestion
OP = "Op"
COMMIT_TS = "_dms_commit_ts"  # a string in the files: cast before ordering
ENVELOPE = (OP, COMMIT_TS, "_rescued_data", "_source_file", "_ingested_at")
