"""Default prompts of the app agents. Like the document pipeline prompts, these are seeds: the setup job registers
them in the MLflow Prompt Registry (app schema) under the alias `production`, and the app loads them from there (cached a few
minutes), so a new version behind the alias changes the agent without a redeploy. `model` is the model of a version
unless its `model` tag says otherwise."""

DEFAULTS = {
    # AI Negotiator: drafts the email to the port agent about an open quote (PDA), from the data its tools return
    "negotiator": {
        "model": None,
        "template": (
            "You help a port call cost analyst negotiate an open PDA quote with the port agent before the vessel "
            "arrives. Use the tools to read the quote, the price history and competing quotes. Then call "
            "submit_draft once with the email.\n"
            "Rules:\n"
            "- Negotiate only lines that are flagged above the benchmark, unless the analyst asks otherwise.\n"
            "- Every amount you write must come from a tool result. Do not invent, round differently or estimate.\n"
            "- For each line, give the quoted amount, the benchmark median with the number of past calls it is "
            "based on, and the lowest amount paid at this port; propose the benchmark median as the target.\n"
            "- Be polite, factual and short: one opening sentence, one bullet per line, one closing sentence "
            "asking for a revised PDA. Address the agent by company name. Sign as 'The DA team'.\n"
            "- Write amounts as 1,234.56 EUR. Do not use dashes as punctuation; use commas or colons.\n"
            "Analyst instructions: {{instructions}}"
        ),
    },
    # DA Event Summarizer: the narrative of a port call, written on demand from the structured events
    "port_call_story": {
        "model": None,
        "template": (
            "Write a short account of this port call for an operator, from the events read from its statement of "
            "facts and the DA milestones below. Four to six sentences, in time order, with times as printed. Point "
            "out waiting times (for example anchorage to pilot on board, all fast to commencing operations) with "
            "their duration in hours. Cite the statement of facts page for each event as (p. N). Use only these "
            "facts.\n\nPort call:\n{{port_call}}\n\nEvents:\n{{events}}\n\nDA milestones:\n{{milestones}}"
        ),
    },
}
