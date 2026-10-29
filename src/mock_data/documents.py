"""PDF documents for a port call, as an agency would send them: proforma, final DA pack, statement of facts.

The final pack is one summary page (all lines, total, bank details) followed by one supplier invoice per line,
so every expense has a page that evidences it. Some calls carry a deliberate problem (see generate.py).
"""
import os
import random
from datetime import timedelta
from decimal import Decimal

from fpdf import FPDF

from reference import NAME_VARIANTS, ROE_TO_USD, SUPPLIERS


def fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


class Doc(FPDF):
    def __init__(self, issuer: str):
        super().__init__(format="A4")
        self.issuer = issuer
        self.set_auto_page_break(True, 20)
        self.set_margins(18, 18, 18)

    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 7, self.issuer, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(180, 180, 180)
        self.line(18, self.get_y() + 1, 192, self.get_y() + 1)
        self.ln(5)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 6, f"Page {self.page_no()}", align="R")

    def title_block(self, title: str, rows: list):
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        for k, v in rows:
            self.cell(42, 6, k)
            self.cell(0, 6, str(v), new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def table(self, rows: list, currency: str, total: Decimal):
        self.set_font("Helvetica", "B", 10)
        self.cell(120, 7, "Description", border="B")
        self.cell(0, 7, f"Amount ({currency})", border="B", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        for name, amount in rows:
            self.cell(120, 7, name)
            self.cell(0, 7, fmt(amount), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 10)
        self.cell(120, 8, "TOTAL", border="T")
        self.cell(0, 8, f"{currency} {fmt(total)}", border="T", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)


def _common(call):
    v, p = call["vessel"], call["port"]
    return [("Vessel", f"MV {v['vessel_name']} (IMO {v['imo']})"), ("Gross tonnage", f"{v['gross_tonnage']:,}"),
            ("Port", f"{p[2]}, {p[3]} ({p[1]})"), ("Principal", call["buyer"])]


def proforma(call) -> bytes:
    doc = Doc(call["agency"])
    doc.add_page()
    doc.title_block("PROFORMA DISBURSEMENT ACCOUNT", [
        ("Reference", f"PDA-{call['pda_id']}"), ("Date", call["pda_submitted"].strftime("%d %b %Y")), *_common(call),
        ("ETA", call["eta"].strftime("%d %b %Y %H:%M")), ("Currency", call["currency"])])
    variants = lambda c: NAME_VARIANTS[c[1]][call["agent"]["company_id"] % len(NAME_VARIANTS[c[1]])]  # noqa: E731
    rows = [(variants(c), call["quotes"][c[1]]) for c in call["lines"]]
    doc.table(rows, call["currency"], sum(call["quotes"].values()))
    doc.set_font("Helvetica", "", 9)
    doc.multi_cell(0, 5, "Estimate based on the port tariff in force. Valid for 30 days. "
                         "Final costs will be invoiced on the final disbursement account.")
    return bytes(doc.output())


def final_pack(call) -> bytes:
    rng = random.Random(call["rng_seed"] + 1)
    anomaly, currency = call["anomaly"], call["currency"]
    agent = call["agent"]
    invoice_currency = "USD" if anomaly == "currency_mismatch" else currency
    rate = Decimal(str(ROE_TO_USD[currency])) if invoice_currency != currency else Decimal(1)
    finals = call["finals"]
    differs, missing = call["differs"], call["missing"]

    account, swift = agent["iban"], agent["swift"]
    if anomaly == "wrong_iban":
        account = agent["iban"][:4] + "".join(rng.choice("0123456789") for _ in range(len(agent["iban"]) - 4))
    elif anomaly == "domestic_account":
        account = agent["iban"][-10:]
    elif anomaly == "swift_8_vs_11":
        swift = swift[:8] if len(swift) == 11 else swift + "XXX"

    doc = Doc(call["agency"])
    doc.add_page()
    doc.title_block("FINAL DISBURSEMENT ACCOUNT", [
        ("Reference", f"FDA-{call['fda_id']}"), ("Date", call["fda_submitted"].strftime("%d %b %Y")), *_common(call),
        ("Arrived / sailed", f"{call['eta']:%d %b %Y %H:%M} / {call['etd']:%d %b %Y %H:%M}"), ("Currency", currency)])
    names = {c[1]: NAME_VARIANTS[c[1]][agent["company_id"] % len(NAME_VARIANTS[c[1]])] for c in call["lines"]}
    doc.table([(names[c[1]], finals[c[1]]) for c in call["lines"]], currency, sum(finals.values()))
    doc.set_font("Helvetica", "B", 10)
    doc.cell(0, 7, "Please remit to", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    label = "Account no." if anomaly == "domestic_account" else "IBAN"
    for k, v in [("Beneficiary", call["agency"]), ("Bank", agent["bank_name"]), (label, account), ("SWIFT / BIC", swift)]:
        doc.cell(42, 6, k)
        doc.cell(0, 6, v, new_x="LMARGIN", new_y="NEXT")

    for n, c in enumerate(call["lines"], start=1):
        name = c[1]
        if name == missing:
            continue
        amount = (finals[name] * (Decimal("1.04") if name == differs else 1) / rate).quantize(Decimal("0.01"))
        supplier = call["agency"] if SUPPLIERS[name] == "agency" else f"{call['port'][2]} {SUPPLIERS[name]}"
        doc.issuer = supplier  # the header of the next page shows the supplier
        doc.add_page()
        doc.title_block("INVOICE", [
            ("Invoice no.", f"{call['port'][1]}-{call['fda_id']}-{n:02d}"),
            ("Date", (call["etd"] + timedelta(days=1)).strftime("%d %b %Y")),
            ("Bill to", f"{call['agency']} as agents for MV {call['vessel']['vessel_name']}"),
            ("Port call", f"{call['port'][2]}, {call['eta']:%d %b %Y}")])
        doc.table([(names[name], amount)], invoice_currency, amount)
    return bytes(doc.output())


def statement_of_facts(call) -> bytes:
    eta, etb, etd = call["eta"], call["etb"], call["etd"]
    events = [("Arrived at anchorage", eta), ("Notice of readiness tendered", eta + timedelta(minutes=30)),
              ("Pilot on board (inbound)", etb - timedelta(minutes=90)), ("All fast", etb),
              ("Commenced operations", etb + timedelta(hours=2)), ("Completed operations", etd - timedelta(hours=3)),
              ("Pilot on board (outbound)", etd - timedelta(minutes=40)), ("Sailed", etd)]
    doc = Doc(call["agency"])
    doc.add_page()
    doc.title_block("STATEMENT OF FACTS", [("Reference", f"SOF-{call['fda_id']}"), *_common(call)])
    doc.set_font("Helvetica", "B", 10)
    doc.cell(60, 7, "Date and time (local)", border="B")
    doc.cell(0, 7, "Event", border="B", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    for name, ts in events:
        doc.cell(60, 7, ts.strftime("%d %b %Y %H:%M"))
        doc.cell(0, 7, name, new_x="LMARGIN", new_y="NEXT")
    return bytes(doc.output())


def write_all(calls: list, root: str) -> int:
    """All documents of a DA sit under proforma/<proforma_id>/<file_item_id>.pdf, as file_item.s3_key says."""
    n = 0
    for call in calls:
        folder = os.path.join(root, "proforma", str(call["pda_id"]))
        os.makedirs(folder, exist_ok=True)
        for family, render in [("pda_quote", proforma), ("final_pack", final_pack), ("sof", statement_of_facts)]:
            with open(os.path.join(folder, f"{call['files'][family]}.pdf"), "wb") as f:
                f.write(render(call))
            n += 1
    return n
