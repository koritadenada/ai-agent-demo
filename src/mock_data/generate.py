"""Mock data for the DA database, written exactly where AWS DMS and the document store put it.

  --mode full_load  every table as DMS full-load Parquet (<schema>/<table>/LOAD00000001.parquet) plus the PDFs of
                    the most recent port calls (proforma/<proforma_id>/<file_item_id>.pdf)
  --mode cdc        one DMS CDC batch (<schema>/<table>/<yyyymmdd-hhmmssfff>.parquet) with inserts, updates and
                    deletes, for example appointment 88213 moving from IN_PROCESS to CANCELLED

The flow follows the platform: request case -> requests for quotation -> quotations -> port call -> appointment
(agent recipient) -> proforma (PDA) -> evaluation (FDA) -> analyst verifications, with documents linked through
file_item. Every row carries the DMS envelope (Op, _dms_commit_ts as a string). The same --seed gives the same data.
"""
import argparse
import inspect
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pyarrow as pa
import pyarrow.parquet as pq

# Sibling modules: serverless jobs run the script without __file__, the code object still knows its path
sys.path.insert(0, os.path.dirname(os.path.abspath(inspect.currentframe().f_code.co_filename)))
import documents  # noqa: E402
from reference import (AGENCY_NAMES, BANKS, BUYER_NAMES, CATEGORIES, FLAGS, NAME_VARIANTS, PORTS,  # noqa: E402
                       VESSEL_TYPES, VESSEL_WORDS)
from source_schema import T, schema  # noqa: E402

REF_DATE = datetime(2026, 10, 28)            # "today" of the mock platform
FULL_LOAD_TS = datetime(2026, 10, 15, 6, 0)  # when the DMS full load ran
FIRST_CALL = datetime(2025, 1, 5)
N_PORT_CALLS = 420
N_DOCUMENT_CALLS = 24
EUR_PER = {"EUR": Decimal("1.000000"), "USD": Decimal("0.925926")}  # rate_eur: EUR per unit of the DA currency

# The line followed end to end in the architecture page (docs/architecture.html, "One line" tab)
SHOWCASE = dict(port_call_id=20217, port_id=1, vessel_id=3007, gt=32400, quote="2500.00", final="2730.00")
APPOINTMENT_CANCELLED = 88213  # the appointment the CDC batch cancels


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iban(country: str, rng: random.Random) -> str:
    """A syntactically valid IBAN (mod-97 check digits) for mock bank accounts."""
    bban = "".join(rng.choice("0123456789") for _ in range(14))
    digits = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{country}{98 - int(digits) % 97:02d}{bban}"


class Db:
    def __init__(self):
        self.rows = {t: [] for t in T}
        self.seq = {}

    def next_id(self, name, start):
        self.seq[name] = self.seq.get(name, start - 1) + 1
        return self.seq[name]

    def add(self, table, **row):
        self.rows[table].append(row)
        return row


def build(seed: int):
    rng = random.Random(seed)
    db = Db()
    t0 = datetime(2024, 6, 1)

    port = {}
    for pid, code, name, country, region, currency, mult in PORTS:
        port[pid] = db.add("port", id=pid, unlocode=code, name=name, country=country, region=region,
                           default_currency=currency, version=1, creation_date=t0, _mult=mult)
    cat = {}
    for cid, name, domain, desc, base, scales, _ in CATEGORIES:
        section = "HUSBANDRY" if domain == "husbandry" else "PORT_EXPENSES"
        # Aliases agencies use on their templates, kept as data so the page mapping recognises them (e.g. CTM)
        aliases = ", ".join(v for v in NAME_VARIANTS[name] if v != name)
        db.add("expense_category", id=cid, name=name, section=section, description=f"{desc}. Also written as: {aliases}",
               version=1)
        cat[name] = dict(base=base, scales=scales, section=section)
    for i, name in enumerate(BUYER_NAMES):
        db.add("buyer", id=i + 1, name=name, company_type=["SHIPOWNER", "OPERATOR", "CHARTERER"][i % 3],
               country=rng.choice(["Greece", "Cyprus", "Germany", "Norway", "Singapore", "Denmark"]), version=1,
               creation_date=t0)

    # Two agency offices per port, each with its own bank account
    agents_by_port = {}
    sid, bid = 1001, 9001
    for pid, _, pname, _, _, currency, _ in PORTS:
        for aname in rng.sample(AGENCY_NAMES, 2):
            country, bank, swift = rng.choice(BANKS[currency])
            sup = db.add("supplier", id=sid, name=f"{aname} {pname}", company_type="AGENT", country=port[pid]["country"],
                         port_id=pid, version=1, creation_date=t0)
            number = iban(country, rng)
            acc = db.add("bank_account", id=bid, supplier_id=sid, bank_name=bank, iban=number, account_number=number[-10:],
                         swift=swift + rng.choice(["", "XXX"]), currency=currency, version=1, creation_date=t0)
            agents_by_port.setdefault(pid, []).append(dict(supplier=sup, account=acc, agency=aname,
                                                           agency_no=AGENCY_NAMES.index(aname)))
            sid, bid = sid + 1, bid + 1

    vessels = {}
    for i in range(60):
        vid = 3001 + i
        vtype = rng.choice(list(VESSEL_TYPES))
        gt = rng.randint(6000, 160000) if vtype != "general cargo" else rng.randint(4000, 30000)
        if vid == SHOWCASE["vessel_id"]:
            vtype, gt = "bulk carrier", SHOWCASE["gt"]
        vessels[vid] = db.add("vessel", id=vid, imo=str(9300000 + rng.randint(0, 699999)),
                              name=f"{rng.choice(VESSEL_WORDS)} {rng.choice(VESSEL_WORDS)}", vessel_type=vtype,
                              gross_tonnage=gt, dwt=int(gt * rng.uniform(1.5, 1.9)), flag=rng.choice(FLAGS),
                              version=1, creation_date=t0, _owner=rng.randint(1, len(BUYER_NAMES)))

    def expected(pid, cname, vtype, gt):
        c = cat[cname]
        return c["base"] * port[pid]["_mult"] * VESSEL_TYPES[vtype] * ((gt / 25000) ** 0.6 if c["scales"] else 1.0)

    def variant(cname, agency_no):
        v = NAME_VARIANTS[cname]
        return v[agency_no % len(v)]

    span = (REF_DATE + timedelta(days=12) - FIRST_CALL).total_seconds()
    calls = {}
    for i in range(N_PORT_CALLS):
        pcid, appt_id = 20001 + i, 88001 + i
        eta = FIRST_CALL + timedelta(seconds=span * i / N_PORT_CALLS + rng.uniform(0, 36000))
        vid = rng.choice(list(vessels))
        pid = rng.choices([p[0] for p in PORTS], weights=[9, 7, 6, 8, 5, 4, 4, 3, 5, 6, 4, 3, 3, 2, 2])[0]
        if pcid == SHOWCASE["port_call_id"]:
            vid, pid, eta = SHOWCASE["vessel_id"], SHOWCASE["port_id"], datetime(2026, 10, 2, 7, 30)
        if appt_id == APPOINTMENT_CANCELLED:  # keep that call in the future so its appointment is open
            eta = REF_DATE + timedelta(days=8, hours=5)
        v = vessels[vid]
        buyer_id, currency = v["_owner"], port[pid]["default_currency"]
        etb = eta + timedelta(hours=rng.uniform(2, 30))
        etd = etb + timedelta(hours=rng.uniform(18, 96))
        cancelled = rng.random() < 0.03 and pcid != SHOWCASE["port_call_id"] and appt_id != APPOINTMENT_CANCELLED
        status = "CANCELLED" if cancelled else "COMPLETED" if etd < REF_DATE else "IN_PORT" if eta < REF_DATE else "PLANNED"
        lines = [c for c in CATEGORIES if c[6] or rng.random() < 0.35]

        # Request case: one RFQ and one quotation per agent at the port; the buyer accepts one
        rc_created = eta - timedelta(days=20)
        rc = db.add("request_case", id=100001 + i, buyer_id=buyer_id, vessel_id=vid, port_id=pid,
                    state="OPEN" if status == "PLANNED" else "CLOSED", date_in=eta, currency=currency,
                    rate=EUR_PER[currency], comments=None, creation_date=rc_created,
                    last_update_date=rc_created + timedelta(days=3), conf_hide_vessel_name=False, version=2,
                    payment_terms="30 days")
        offers = []
        for a in agents_by_port[pid]:
            factor = rng.gauss(1.0, 0.07)
            amounts = {c[1]: money(expected(pid, c[1], v["vessel_type"], v["gross_tonnage"]) * factor * rng.gauss(1.0, 0.03))
                       for c in lines}
            offers.append((sum(amounts.values()), a, amounts))
        offers.sort(key=lambda o: o[0])
        agent = (offers[0] if rng.random() < 0.8 else offers[1])[1]
        for _, a, amounts in offers:
            sent = rc_created + timedelta(hours=rng.uniform(4, 48))
            rfq = db.add("request_for_quotation", id=db.next_id("rfq", 110001), request_case_id=rc["id"],
                         supplier_id=a["supplier"]["id"], state="ANSWERED", creation_date=rc_created, submission_date=sent,
                         last_update_date=rc_created + timedelta(days=2), version=2, conversation_id=None)
            q = db.add("quotation", id=db.next_id("quotation", 120001), request_case_id=rc["id"],
                       request_for_quotation_id=rfq["id"], state="ACCEPTED" if a is agent else "REJECTED",
                       submitter_id=None, quoter_id=a["supplier"]["id"], submission_date=sent, quotation_date=sent,
                       comments=None, observer_state="DONE", observer_pokes=rng.randint(0, 3),
                       observer_first_poke_date=None, observer_last_poke_date=None, version=3,
                       automatic=rng.random() < 0.2)
            a["quotation"], a["quote_lines"] = q, {}
            for c in lines:
                a["quote_lines"][c[1]] = db.add(
                    "quotation_expense", id=db.next_id("quotation_expense", 1300001), request_case_id=rc["id"],
                    request_for_quotation_id=rfq["id"], quotation_id=q["id"], state="ACTIVE",
                    name=variant(c[1], a["agency_no"]), section=cat[c[1]]["section"], category_id=c[0],
                    is_renegotiate=False, is_supplier_added=False, amount=amounts[c[1]], unit=Decimal(1), comments=None,
                    key=None, creation_date=sent, ref_port_expense_id=None, ref_expense_catalogue_item_id=None, version=1,
                    unit_type="PER_CALL", request_expense_id=None, port_analysis_expense_id=None, is_excluded=False)

        db.add("port_call", id=pcid, voyage_id=700000 + i, state=status, buyer_id=buyer_id, submitter_id=None,
               vessel_id=vid, port_id=pid, creation_date=rc_created + timedelta(days=4), last_update_date=min(etd, REF_DATE),
               schedule_date_in_status="ACTUAL" if eta < REF_DATE else "ESTIMATED", schedule_date_in=eta,
               schedule_date_out_status="ACTUAL" if etd < REF_DATE else "ESTIMATED", schedule_date_out=etd,
               schedule_dates_range=None, position=None, assignment_id=None, max_amount_currency=currency,
               max_amount_value=money(offers[-1][0] * Decimal("1.15")), is_free_da=False, comments=None, version=4,
               sailing_date=etd.date(), brokers_estimate_amount_currency=None, brokers_estimate_amount_value=None,
               is_tbn=False, linked_port_call_id=None, veson_port_name=port[pid]["name"], port_changed=False,
               previous_port_name=None, ops_coordinator_email="ops.coordinator@buyer.example",
               ops_coordinator_profile_id=None)
        db.add("port_call_request_case", port_call_id=pcid, request_case_id=rc["id"])

        appt_state = {"COMPLETED": "COMPLETED", "IN_PORT": "CONFIRMED", "CANCELLED": "CANCELLED"}.get(status)
        if appt_state is None:
            appt_state = "IN_PROCESS" if (rng.random() < 0.5 or appt_id == APPOINTMENT_CANCELLED) else "CONFIRMED"
        appt_created = eta - timedelta(days=12)
        db.add("appointment", id=appt_id, port_call_id=pcid, buyer_id=buyer_id, submitter_id=None, vessel_id=vid,
               state=appt_state, creation_date=appt_created, submission_date=appt_created + timedelta(hours=2),
               last_update_date=min(eta - timedelta(days=9), REF_DATE), eta_date=eta, email_configuration_id=None,
               observer_state="DONE", observer_pokes=rng.randint(0, 2), observer_first_poke_date=None,
               observer_last_poke_date=None, version=3, conversation_id=None,
               cancellation_reason="Voyage cancelled by the owner" if cancelled else None, dashboard_status=appt_state,
               request_case_id=rc["id"], has_new_expenses=False, proforma_grouping_type="SINGLE",
               uses_port_analysis_expenses=False)
        db.add("appointment_recipient", id=89001 + i, appointment_id=appt_id, supplier_id=agent["supplier"]["id"],
               company_type="AGENT", version=1)
        db.add("appointment_agent_recipient", id=89001 + i, agent_type="OWNER_AGENT")
        if cancelled:
            continue

        # Proforma (PDA): the accepted quotation becomes the quote
        quotes = {c[1]: agent["quote_lines"][c[1]]["amount"] for c in lines}
        finals = {}
        for c in lines:
            r = rng.random()
            factor = rng.uniform(1.12, 1.35) if r < 0.08 else rng.uniform(0.85, 0.95) if r < 0.13 else rng.gauss(1.015, 0.03)
            finals[c[1]] = money(float(quotes[c[1]]) * factor)
        if pcid == SHOWCASE["port_call_id"]:
            quotes["Pilotage"], finals["Pilotage"] = Decimal(SHOWCASE["quote"]), Decimal(SHOWCASE["final"])
        pda_submitted = eta - timedelta(days=5)
        pda = db.add("proforma", id=50001 + i, port_call_id=pcid, appointment_id=appt_id, submitter_id=None,
                     state="APPROVED" if pda_submitted + timedelta(days=1) < REF_DATE else "SUBMITTED",
                     creation_date=pda_submitted - timedelta(days=1), submission_date=pda_submitted, currency=currency,
                     rate=EUR_PER[currency], terminal_id=None, berth_id=None, comments=None, revision=1, version=3,
                     type="PDA", bank_account_id=agent["account"]["id"], invoice_number=f"PDA-{50001 + i}",
                     invoice_date=pda_submitted, creation_date_rate=EUR_PER[currency], rate_eur=EUR_PER[currency],
                     quotation_id=agent["quotation"]["id"], rfq_to_da_rate=Decimal(1), pricelist_id=None,
                     pricelist_to_da_rate=None, has_expenses_from_linked_pdas=False, expenses_type="STANDARD",
                     linked_group_id=None, split_actor_id=None, parent_proforma_id=None,
                     attachment_validation_file_id=None, split_pda_fda_attachments=False)
        pe = {}
        for c in lines:
            q = quotes[c[1]]
            pe[c[1]] = db.add(
                "proforma_expense", id=db.next_id("proforma_expense", 1), port_call_id=pcid, proforma_id=pda["id"],
                state="ACTIVE", name=variant(c[1], agent["agency_no"]), section=cat[c[1]]["section"], category_id=c[0],
                comments=rng.choice([None, "As per tariff"]), creation_date=pda["creation_date"], price_amount=q,
                price_surcharges=Decimal(0), price_discount=Decimal(0), ref_port_expense_id=None,
                ref_expense_catalogue_item_id=None, price_currency=currency, version=2, has_attachment=False,
                full_amount=q, contract_discount=Decimal(0), buyer_contract_id=None, unit=Decimal(1),
                unit_type="PER_CALL", expense_category_group_id=None, calculate_comments=None,
                quotation_expense_id=agent["quote_lines"][c[1]]["id"], is_custom=False, agent_submitted_tariff=None,
                expense_deviation_notification_sent=False, ignore_deviation=False, deleted=False,
                port_analysis_expense_id=None)
        if status != "COMPLETED":
            continue
        fda_submitted = etd + timedelta(days=rng.uniform(3, 9))
        if fda_submitted > REF_DATE:
            continue
        approved = fda_submitted + timedelta(hours=rng.uniform(20, 200))
        if approved > REF_DATE - timedelta(days=1):
            ev_state, approved = "SUBMITTED", None
        else:
            ev_state = "PAID" if approved < REF_DATE - timedelta(days=5) else "APPROVED"
        ev = db.add("evaluation", id=60001 + i, port_call_id=pcid, appointment_id=appt_id, proforma_id=pda["id"],
                    creation_date=fda_submitted - timedelta(days=1), state=ev_state, modifier_id=None,
                    last_update_date=approved or fda_submitted, currency=currency, rate=EUR_PER[currency],
                    terminal_id=None, berth_id=None,
                    total_remitted_amount=sum(finals.values()) if ev_state == "PAID" else None,
                    payment_due_date=fda_submitted + timedelta(days=30), version=4,
                    bank_account_id=agent["account"]["id"], invoice_number=f"FDA-{60001 + i}", invoice_date=fda_submitted,
                    approval_date=approved, dashboard_status=ev_state, assignee_id=None, remittance_percentage=100,
                    payment_instructions_id=None, integration_file_item_id=None, payment_instructions_updated=False,
                    payment_due_date_updated=False, rate_eur=EUR_PER[currency], iso_discount_amount=None,
                    green_award_discount_amount=None, esi_discount_amount=None, protocol_event_sent=False,
                    deletion_profile_id=None, deletion_date=None, deletion_reason=None, other_reason_text=None,
                    uses_port_analysis_expenses=False)
        ee = {}
        for c in lines:
            ee[c[1]] = db.add(
                "expense_evaluation", id=db.next_id("expense_evaluation", 400001), parent_id=None, buyer_id=buyer_id,
                port_call_id=pcid, appointment_id=appt_id, proforma_id=pda["id"], evaluation_id=ev["id"],
                proforma_expense_id=pe[c[1]]["id"], type="EXPENSE", name=variant(c[1], agent["agency_no"]),
                section=cat[c[1]]["section"], category_id=c[0], creation_date=ev["creation_date"],
                accounting_code_id=None, version=2, price_currency=currency, price_amount=finals[c[1]],
                price_surcharges=Decimal(0), price_discount=Decimal(0), department_id=None, comments=None,
                deleted_on=None, dashboard_status=ev_state, mro_type=None, unit=Decimal(1), unit_type="PER_CALL",
                expense_category_group_id=None, ref_port_expense_id=None, ref_expense_catalogue_item_id=None,
                port_analysis_expense_id=None, is_platform_fee=False, merged_into_id=None, is_active=True,
                is_excluded_from_historical_data=False)
        # The platform's own service fee: a final line with no quote, excluded from history and benchmarks
        db.add("expense_evaluation", **{**ee[lines[0][1]], "id": db.next_id("expense_evaluation", 400001),
                                       "proforma_expense_id": None, "type": "FEE", "name": "Platform service fee",
                                       "category_id": None, "section": None, "price_amount": money(150),
                                       "is_platform_fee": True, "is_excluded_from_historical_data": True})
        calls[pcid] = dict(port_call_id=pcid, appointment_id=appt_id, buyer_id=buyer_id, pda_id=pda["id"],
                           fda_id=ev["id"], ev=ev, ee=ee, quotes=quotes, finals=finals, currency=currency, lines=lines,
                           port=(pid, port[pid]["unlocode"], port[pid]["name"], port[pid]["country"]),
                           vessel=dict(vessel_name=v["name"], imo=v["imo"], gross_tonnage=v["gross_tonnage"]),
                           agent=dict(company_id=agent["agency_no"], iban=agent["account"]["iban"],
                                      swift=agent["account"]["swift"], bank_name=agent["account"]["bank_name"]),
                           agency=agent["agency"], buyer=BUYER_NAMES[buyer_id - 1], eta=eta, etb=etb, etd=etd,
                           fda_submitted=fda_submitted, pda_submitted=pda_submitted)

    doc_calls = add_documents(db, calls, seed)
    add_verifications(db, calls, doc_calls, seed)
    return db, doc_calls


def add_documents(db, calls, seed):
    """PDFs for the most recent closed port calls, with a few deliberate problems to find."""
    recent = sorted((c for c in calls.values() if c["port_call_id"] != SHOWCASE["port_call_id"]),
                    key=lambda c: c["fda_submitted"], reverse=True)[: N_DOCUMENT_CALLS - 1]
    doc_calls = [calls[SHOWCASE["port_call_id"]]] + recent
    anomalies = ["none", "invoice_differs", "invoice_differs", "invoice_differs", "missing_invoice", "missing_invoice",
                 "wrong_iban", "wrong_iban", "domestic_account", "swift_8_vs_11", "split_in_out"]
    eur = next(c for c in recent if c["currency"] == "EUR")
    for n, call in enumerate(doc_calls):
        call["anomaly"] = "currency_mismatch" if call is eur else anomalies[n] if n < len(anomalies) else "none"
        call["rng_seed"] = seed * 1000 + n
        drng = random.Random(call["rng_seed"])
        call["differs"] = drng.choice(call["lines"])[1] if call["anomaly"] == "invoice_differs" else None
        call["missing"] = drng.choice(call["lines"][1:])[1] if call["anomaly"] == "missing_invoice" else None
        call["files"] = {}
        for family, link, ts in [("pda_quote", "proforma_attachments", call["pda_submitted"]),
                                 ("final_pack", "proforma_attachments", call["fda_submitted"]),
                                 ("sof", "proforma_statement_of_facts", call["fda_submitted"])]:
            fid = db.next_id("file_item", 1348001)
            db.add("file_item", id=fid, s3_key=f"proforma/{call['pda_id']}/{fid}.pdf", file_name=f"{family}.pdf",
                   content_type="application/pdf", size_bytes=None, creation_date=ts)
            db.add(link, file_item_id=fid, proforma_id=call["pda_id"])
            call["files"][family] = fid
        for c in call["lines"]:
            if c[1] != call["missing"]:  # the supporting invoice is a page of the final pack
                db.add("expense_evaluation_attachments", file_item_id=call["files"]["final_pack"],
                       expense_evaluation_id=call["ee"][c[1]]["id"])
    return doc_calls


def add_verifications(db, calls, doc_calls, seed):
    """What a DA analyst concluded for each line of an approved FDA: the ground truth for the automated checks."""
    doc_by_fda = {c["fda_id"]: c for c in doc_calls}
    for call in calls.values():
        ev = call["ev"]
        if ev["approval_date"] is None:
            continue
        vrng = random.Random(seed + ev["id"])
        db.add("evaluation_verification", id=db.next_id("evaluation_verification", 610001), buyer_id=call["buyer_id"],
               port_call_id=call["port_call_id"], appointment_id=call["appointment_id"], proforma_id=call["pda_id"],
               evaluation_id=ev["id"], state="VERIFIED", department="OPERATIONS", creation_date=call["fda_submitted"],
               activation_date=call["fda_submitted"], verification_date=ev["approval_date"] - timedelta(hours=2),
               sign_off_role="DA_ANALYST", version=2, department_id=None, pre_approval=False)
        doc = doc_by_fda.get(ev["id"], {})
        for c in call["lines"]:
            q, f = call["quotes"][c[1]], call["finals"][c[1]]
            if doc.get("anomaly") == "currency_mismatch":
                kind = "CURRENCY_MISMATCH"
            elif c[1] == doc.get("missing"):
                kind = "MISSING_SUPPORTING_DOCUMENT"
            elif c[1] == doc.get("differs"):
                kind = "AMOUNT_MISMATCH"
            elif f > q * Decimal("1.02"):
                kind = "OVERCHARGE" if vrng.random() < 0.9 else "NONE"    # analysts miss a few
            elif f < q * Decimal("0.98"):
                kind = "UNDERCHARGE" if vrng.random() < 0.7 else "NONE"
            else:
                kind = "NONE"
            db.add("expense_evaluation_verification", id=db.next_id("expense_evaluation_verification", 620001),
                   buyer_id=call["buyer_id"], port_call_id=call["port_call_id"], appointment_id=call["appointment_id"],
                   proforma_id=call["pda_id"], evaluation_id=ev["id"], expense_evaluation_id=call["ee"][c[1]]["id"],
                   state="VERIFIED", creation_date=call["fda_submitted"], verification_date=ev["approval_date"],
                   amount=f, discount_type=None, discount_amount=None, discrepancy_type=kind,
                   discrepancy_amount=(f - q) if kind != "NONE" else Decimal(0), version=1)


def cdc_batch(db: Db, commit_ts: datetime) -> dict:
    """One DMS CDC batch. Op U carries the full row after the update, Op D the row before the delete."""
    def bump(r, **kw):
        return dict(r, version=r["version"] + 1, **kw)

    appt = next(r for r in db.rows["appointment"] if r["id"] == APPOINTMENT_CANCELLED)
    out = {"appointment": [("U", bump(appt, state="CANCELLED", dashboard_status="CANCELLED",
                                      cancellation_reason="Voyage orders changed", last_update_date=commit_ts))]}
    out["evaluation"] = [("U", bump(r, state="APPROVED", dashboard_status="APPROVED", approval_date=commit_ts,
                                    last_update_date=commit_ts))
                         for r in db.rows["evaluation"] if r["state"] == "SUBMITTED"][:3]
    acc = db.rows["bank_account"][-1]
    out["bank_account"] = [("U", bump(acc, iban=iban(acc["iban"][:2], random.Random(7))))]
    open_pda = next(r for r in db.rows["proforma"] if r["state"] == "SUBMITTED")
    out["proforma_expense"] = [("D", next(r for r in db.rows["proforma_expense"] if r["proforma_id"] == open_pda["id"]))]
    # A change committed while the full load was running: its commit time is earlier than the full-load copy time.
    # The table has no version column, so only "full load first" ordering applies it correctly.
    rec = next(r for r in db.rows["appointment_agent_recipient"] if r["id"] == APPOINTMENT_CANCELLED + 1000)
    out["appointment_agent_recipient"] = [("U", dict(rec, agent_type="CHARTERER_AGENT",
                                                     _commit_ts=FULL_LOAD_TS - timedelta(minutes=2)))]
    return out


def write_table(dms_path, source_schema, table, rows, ops, commit_ts, file_name):
    def stamp(r):  # a row can carry its own source commit time (_commit_ts), as DMS writes it
        return r.get("_commit_ts", commit_ts).strftime("%Y-%m-%d %H:%M:%S.%f")
    records = [{"Op": op, "_dms_commit_ts": stamp(r), **{k: v for k, v in r.items() if not k.startswith("_")}}
               for op, r in zip(ops, rows)]
    folder = os.path.join(dms_path, source_schema, table)
    os.makedirs(folder, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records, schema=schema(table)), os.path.join(folder, file_name))
    print(f"{table}: {len(records)} rows -> {source_schema}/{table}/{file_name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full_load", "cdc"], default="full_load")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dms-path", required=True)
    ap.add_argument("--documents-path", required=True)
    ap.add_argument("--source-schema", default="da_schema")
    a = ap.parse_args()

    db, doc_calls = build(a.seed)
    if a.mode == "full_load":
        for table, rows in db.rows.items():
            write_table(a.dms_path, a.source_schema, table, rows, ["I"] * len(rows), FULL_LOAD_TS, "LOAD00000001.parquet")
        print(f"documents: {documents.write_all(doc_calls, a.documents_path)} PDFs -> {a.documents_path}")
        return

    commit_ts = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    name = commit_ts.strftime("%Y%m%d-%H%M%S") + "000.parquet"
    for table, changes in cdc_batch(db, commit_ts).items():
        write_table(a.dms_path, a.source_schema, table, [r for _, r in changes], [op for op, _ in changes], commit_ts, name)


if __name__ == "__main__":
    main()
