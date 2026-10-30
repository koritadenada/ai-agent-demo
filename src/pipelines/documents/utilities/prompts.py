"""Default prompts of every model call in the document pipeline.

These are seeds, not the source of truth: the setup job registers them in the MLflow Prompt Registry (Unity
Catalog) under the alias `production`, and the pipeline loads them from there on every run. To change a prompt or
the model behind it, register a new version and move the alias: no code change, no deploy. Point a second alias
(for example `challenger`) at another version to compare them on the same documents.

Placeholders use double braces. `model` applies to ai_query steps; ai_classify and ai_extract use their built-in
model, so for them the instructions are what you iterate on.
"""

DEFAULTS = {
    # ai_classify: which kind of document this is, from its first page
    "document_type": {
        "model": None,
        "template": (
            "These are documents of a port call disbursement account (DA). A PDA quote is the agent's estimate "
            "before arrival; a final DA pack has the final amounts, the bank details and one supplier invoice per "
            "expense; a statement of facts lists the times of arrival, operations and departure."
        ),
    },
    # ai_query: which expense line of this DA a page evidences
    "page_map": {
        "model": "databricks-gpt-5-mini",
        "template": (
            "You review one page of a final disbursement account pack for a port call.\n"
            "Decide whether the page is the summary (all expense lines and bank details), a supporting invoice for "
            "ONE expense, or something else. For a supporting invoice, pick the expense line of this DA it "
            "evidences, by its id. Agencies name expenses differently, so match on meaning, not on wording. A line "
            "invoiced in parts (for example pilotage in and pilotage out) maps every part to the same line. If no "
            "line fits, use 0. Also give the expense category. Confidence is between 0 and 1.\n\n"
            "Expense lines of this DA (id: name, category, section):\n{{expense_lines}}\n\n"
            "Expense categories:\n{{categories}}\n\n"
            "Page text:\n{{page_text}}"
        ),
    },
    # ai_extract: the amount on one supporting invoice
    "invoice_amount": {
        "model": None,
        "template": (
            "This is one supplier invoice for a port call expense. Read the total amount due on this invoice and "
            "its currency, exactly as printed. Do not convert currencies."
        ),
    },
    # ai_extract: bank details, totals, date and rate of exchange from the summary page
    "bank_details": {
        "model": None,
        "template": (
            "This is the summary page of a final disbursement account. Read the bank details payments go to, the "
            "grand total, its currency and the date of the document. The account can be labelled IBAN, Account "
            "no., Account number, Beneficiary account or A/C; SWIFT can be labelled BIC or SWIFT/BIC. Copy the "
            "account exactly as printed. If a rate of exchange is printed (for example 1 EUR = 1.08 USD), give how "
            "many units of the other currency equal one unit of the document currency; otherwise leave it empty."
        ),
    },
    # ai_query: the timeline of a statement of facts, as structured events (a narrative is written on demand by
    # the chat assistant, so it is not stored here)
    "sof_events": {
        "model": "databricks-gpt-5-mini",
        "template": (
            "List every timed event in this statement of facts, in the order they happened, with the date and time "
            "as printed. Use short event names such as Pilot on board or All fast. Do not invent events.\n\n"
            "Text:\n{{document_text}}"
        ),
    },
}
