// Overview and DA review (Bill Reconciler + Payment Validator).
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { useQuery as useAnalyticsQuery } from '../lib/query';
import { sql } from '@databricks/appkit-ui/js';
import { useSchemas } from '../lib/config';
import { I } from '../lib/icons';
import { ACTION, DECISION, SECTION, VERDICT, list, month, num, when } from '../lib/format';
import {
  Confirm, DecisionPill, DocChips, DocumentViewer, Failed, LinesPill, Loading, PageChip, PaymentPill, Svc, post, useToast,
  type Doc,
} from '../components/ui';

export function Overview() {
  const s = useSchemas();
  const nav = useNavigate();
  const kpi = useAnalyticsQuery('overview_kpis', { gold: s.gold, app: s.app });
  const fdas = useAnalyticsQuery('fdas', { gold: s.gold, app: s.app });
  const quotes = useAnalyticsQuery('quotes', { gold: s.gold, app: s.app });
  const [q, setQ] = useState('');
  if (kpi.error) return <Failed error={kpi.error} />;
  const k = kpi.data?.[0];
  return (
    <>
      <section className="hero">
        <div className="eyebrow">Port call AI agents</div>
        <h1>Check <em>every</em> DA<br />against its documents.</h1>
        <div className="tagline">Quotes benchmarked, invoices read, bank details validated, before money moves.</div>
      </section>
      {!k ? <Loading /> : (
        <div className="kpis">
          <div className="kpi accent"><div className="v">{k.fdas_to_review}<small>of {k.fdas_checked}</small></div><div className="l">Final DAs waiting for a decision</div></div>
          <div className="kpi alert"><div className="v">{k.payments_on_hold}</div><div className="l">Payments on hold: bank details differ</div></div>
          <div className="kpi"><div className="v">{num(k.over_invoiced_eur, 0)}<small>EUR</small></div><div className="l">Invoiced above the quote on checked DAs</div></div>
          <div className="kpi good"><div className="v">{num(k.open_quote_savings_eur, 0)}<small>EUR</small></div><div className="l">To negotiate on {k.open_quotes_flagged} open quotes</div></div>
        </div>
      )}
      <div className="grid g2">
        <div className="card">
          <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.review}Final DAs to decide</h3><Svc name="Bill Reconciler" icon="review" /></div>
          <div className="sub">Every line checked against its quote and its invoice page; bank details checked before payment.</div>
          <div className="list">{(fdas.data ?? []).slice(0, 6).map((f) => (
            <div className="item" key={f.evaluation_id} onClick={() => void nav(`/review/${f.evaluation_id}`)}>
              <div className={`ico${f.hold_payment ? ' red' : ''}`}>{f.hold_payment ? I.bank : I.review}</div>
              <div><div className="t">{f.vessel_name} at {f.port_name}</div><div className="s">{f.agent_name} · port call {f.port_call_id}</div></div>
              <div className="r"><div>{f.hold_payment ? <PaymentPill hold /> : <LinesPill flagged={f.lines_flagged} checked={f.lines_checked} />}</div>
                <div className="s" style={{ marginTop: 4 }}><DecisionPill decision={f.decision} /></div></div>
            </div>
          ))}{fdas.loading && <Loading />}</div>
          <div style={{ marginTop: 12 }}><Link to="/review" className="btn ghost sm">All final DAs</Link></div>
        </div>
        <div className="card">
          <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.deal}Open quotes to negotiate</h3><Svc name="Quote Negotiator" icon="deal" /></div>
          <div className="sub">PDA quotes above what this port usually costs for this vessel size, before the vessel arrives.</div>
          <div className="list">{(quotes.data ?? []).filter((x) => x.flagged_lines).map((x) => (
            <div className="item" key={x.proforma_id} onClick={() => void nav(`/negotiator/${x.proforma_id}`)}>
              <div className="ico green">{I.euro}</div>
              <div><div className="t">{x.vessel_name} at {x.port_name}</div><div className="s">{x.agent_name} · {x.flagged_lines} of {x.lines} lines above the benchmark</div></div>
              <div className="r"><div className="t amt-ok">{num(x.saving_eur)} EUR</div><div className="s">potential saving</div></div>
            </div>
          ))}{quotes.loading && <Loading />}</div>
          <div style={{ marginTop: 12 }}><Link to="/negotiator" className="btn ghost sm">All open quotes</Link></div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 20 }}>
        <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.assistant}Ask the Port Assistant</h3><Svc name="Port Assistant" icon="assistant" /></div>
        <div className="sub">Costs, audits, operations and documents, in plain language, with your own data permissions.</div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); if (q.trim()) void nav('/assistant', { state: { question: q } }); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: which ports were most expensive per call last month?" />
          <button className="btn">{I.send}Ask</button>
        </form>
        {k && <div className="small muted" style={{ marginTop: 12 }}>Agreement of the automated checks with the DA analysts: <b>{num(k.agreement_pct, 1)}%</b> of verified lines.</div>}
      </div>
    </>
  );
}

type Filter = 'todo' | 'hold' | 'decided' | 'all';

export function ReviewList() {
  const s = useSchemas();
  const nav = useNavigate();
  const { data, loading, error } = useAnalyticsQuery('fdas', { gold: s.gold, app: s.app });
  const [filter, setFilter] = useState<Filter>('todo');
  if (error) return <Failed error={error} />;
  const rows = data ?? [];
  const groups: Record<Filter, (r: (typeof rows)[number]) => boolean> = {
    todo: (r) => !r.decision, hold: (r) => !!r.hold_payment, decided: (r) => !!r.decision, all: () => true,
  };
  const shown = rows.filter(groups[filter]);
  return (
    <>
      <div className="pagehead">
        <div><Svc name="Bill Reconciler" icon="review" /> <Svc name="Payment Validator" icon="bank" />
          <h2>Final DA review</h2><p>Each final DA, line by line against the quote and the supplier invoice pages, and the bank details against the platform.</p></div>
        <div className="tabs">{([['todo', 'To review'], ['hold', 'Payment on hold'], ['decided', 'Decided'], ['all', 'All']] as [Filter, string][]).map(([k, t]) => (
          <button key={k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{t}<b>{rows.filter(groups[k]).length}</b></button>
        ))}</div>
      </div>
      {loading ? <Loading /> : (
        <div className="tbl"><table><tbody>
          <tr><th>Vessel and port</th><th>Agent</th><th>Call</th><th className="num">Final DA</th><th>Lines</th><th>Payment</th><th>Decision</th></tr>
          {shown.map((r) => (
            <tr className="row" key={r.evaluation_id} onClick={() => void nav(`/review/${r.evaluation_id}`)}>
              <td><b>{r.vessel_name}</b><div className="exp">{r.port_name} · port call {r.port_call_id}</div></td>
              <td>{r.agent_name}<div className="exp">{r.buyer_name}</div></td>
              <td className="nowrap">{month(r.call_month)}</td>
              <td className="num nowrap">{num(r.final_amount)} <span className="muted small">{r.currency}</span></td>
              <td><LinesPill flagged={r.lines_flagged} checked={r.lines_checked} ofTotal /></td>
              <td><PaymentPill hold={r.hold_payment} /></td>
              <td><DecisionPill decision={r.decision} /></td>
            </tr>
          ))}
          {!shown.length && <tr><td colSpan={7} className="muted">Nothing here.</td></tr>}
        </tbody></table></div>
      )}
    </>
  );
}

type Check = { name: string; status: string; confidence: number | null; explanation: string };

export function ReviewDetail() {
  const id = Number(useParams().id);
  const [version, setVersion] = useState(0);  // bumped after a decision, to read it back
  return <ReviewDetailBody key={version} id={id} onSaved={() => setVersion((v) => v + 1)} />;
}

function ReviewDetailBody({ id, onSaved }: { id: number; onSaved: () => void }) {
  const s = useSchemas();
  const toast = useToast();
  const fdas = useAnalyticsQuery('fdas', { gold: s.gold, app: s.app });
  const lines = useAnalyticsQuery('fda_lines', { gold: s.gold, evaluation_id: sql.bigint(id) });
  const pay = useAnalyticsQuery('fda_payment', { gold: s.gold, evaluation_id: sql.bigint(id) });
  const history = useAnalyticsQuery('fda_decisions', { app: s.app, evaluation_id: sql.bigint(id) });
  const f = fdas.data?.find((x) => x.evaluation_id === id);
  const docs = useAnalyticsQuery('documents', { gold: s.gold, silver: s.silver, evaluation_id: sql.bigint(id), port_call_id: sql.bigint(0) });
  const [open, setOpen] = useState<{ file: number; page: number } | null>(null);
  const [asking, setAsking] = useState<'accept' | 'dispute' | 'hold' | null>(null);
  if (fdas.error || lines.error) return <Failed error={(fdas.error ?? lines.error) as string} />;
  if (!f || !lines.data) return <Loading />;
  const p = pay.data?.[0];
  const checks = list<Check>(p?.field_checks);
  const documents = (docs.data ?? []) as Doc[];
  const pack = documents.find((d) => d.doc_type === 'final_da_pack');
  const shown = open ?? (pack ? { file: pack.file_item_id, page: 1 } : null);
  const bySection: Record<string, typeof lines.data> = {};
  for (const l of lines.data) (bySection[l.expense_section ?? 'OTHER'] ??= []).push(l);
  const sum = (ls: typeof lines.data, k: 'quoted_amount' | 'final_amount') => ls.reduce((a, l) => a + Number(l[k] ?? 0), 0);

  const bank = p && (
    <div className="card">
      <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.bank}Bank details before payment</h3><Svc name="Payment Validator" icon="bank" /></div>
      <div className="sub">What the DA pack says against what the platform has on file. Low-confidence readings never count as a match.</div>
      {checks.map((c) => (
        <div className="check" key={c.name}><span className={`pill ${c.status === 'MATCH' ? 'ok' : 'dispute'}`}>{c.status === 'MATCH' ? 'Match' : 'Differs'}</span>
          <div><div className="n">{c.name}</div><div className="e">{c.explanation}{c.confidence != null ? ` · read with ${num(c.confidence * 100, 0)}% confidence` : ''}</div></div></div>
      ))}
    </div>
  );

  const decide = async (result: { note: string } | null) => {
    const decision = asking;
    setAsking(null);
    if (!result || !decision) return;
    try { await post(`/api/fdas/${id}/decision`, { decision, note: result.note }); toast.show('Decision saved'); onSaved(); }
    catch (e) { toast.show((e as Error).message, true); }
  };
  const ask = { accept: ['Accept final DA', `Accept the final DA of ${f.vessel_name} at ${f.port_name} for payment?`, 'Accept', 'green'],
    dispute: ['Dispute final DA', `Dispute this final DA with ${f.agent_name}? ${f.lines_flagged ?? 0} ${f.lines_flagged === 1 ? 'line was' : 'lines were'} flagged.`, 'Dispute', 'orange'],
    hold: ['Hold payment', 'Hold the payment of this final DA until the bank details are confirmed?', 'Hold payment', 'red'] } as const;

  return (
    <>
      <Link className="back" to="/review">{I.back}All final DAs</Link>
      <div className="pagehead"><div><h2>{f.vessel_name} at {f.port_name}</h2>
        <p>{f.agent_name} for {f.buyer_name} · port call <Link to={`/port-calls/${f.port_call_id}`}>{f.port_call_id}</Link> · {month(f.call_month)}</p></div>
        <div className="row-gap"><DecisionPill decision={f.decision} />{p?.hold_payment && <PaymentPill hold />}</div></div>
      <div className="grid g-main">
        <div className="grid">
          {p?.hold_payment && bank}
          <div className="card flush">
            <div className="head row-gap" style={{ justifyContent: 'space-between' }}><div><h3>{I.review}Quote against final bill</h3>
              <div className="sub" style={{ margin: 0 }}>{f.lines_flagged == null ? 'The lines have not been checked yet' : f.lines_flagged ? `${f.lines_flagged} of ${f.lines_checked} ${f.lines_flagged === 1 ? 'line needs' : 'lines need'} a look` : `All ${f.lines_checked} lines match`}. Click a page to see the invoice.</div></div>
              <Svc name="Bill Reconciler" icon="review" /></div>
            <div className="tbl" style={{ borderRadius: 0, borderLeft: 0, borderRight: 0, borderBottom: 0 }}><table><tbody>
              <tr><th>Expense</th><th className="num">Quoted ({f.currency})</th><th className="num">Final ({f.currency})</th><th>Invoice page</th><th>Check</th></tr>
              {Object.entries(bySection).map(([sec, ls], i) => [
                <tr className="sec" key={`${sec}-h`}><td colSpan={5}>{String.fromCharCode(65 + i)}. {SECTION[sec] ?? sec}</td></tr>,
                ...ls.map((l) => {
                  const cls = ACTION[l.review_action ?? ''] ?? 'muted';
                  const pages = list<number | string>(l.evidence_pages).map(Number);
                  return (
                    <tr key={l.expense_evaluation_id}>
                      <td><b>{l.line_name}</b><div className="exp">{l.explanation}</div></td>
                      <td className="num nowrap">{num(l.quoted_amount)}</td>
                      <td className={`num nowrap amt-${cls}`}>{num(l.final_amount)}</td>
                      <td className="nowrap">{pages.length ? pages.map((pg) => (
                        <PageChip key={pg} page={pg} on={shown?.file === l.file_item_id && shown?.page === pg} onClick={() => l.file_item_id && setOpen({ file: l.file_item_id, page: pg })} />
                      )) : <span className="muted small">none</span>}</td>
                      <td><span className={`pill ${cls}`}>{VERDICT[l.verdict ?? ''] ?? l.verdict}</span>
                        {l.variance_vs_quote_pct != null && Math.abs(l.variance_vs_quote_pct) >= 0.05 && <div className="exp">{l.variance_vs_quote_pct > 0 ? '+' : ''}{num(l.variance_vs_quote_pct, 1)}% vs quote</div>}</td>
                    </tr>
                  );
                }),
                <tr className="subtotal" key={`${sec}-s`}><td>Subtotal</td><td className="num">{num(sum(ls, 'quoted_amount'))}</td><td className="num">{num(sum(ls, 'final_amount'))}</td><td colSpan={2} /></tr>,
              ])}
              <tr className="total"><td>Total</td><td className="num">{num(sum(lines.data, 'quoted_amount'))}</td><td className="num">{num(sum(lines.data, 'final_amount'))}</td><td colSpan={2} /></tr>
            </tbody></table></div>
          </div>
          {!p?.hold_payment && bank}
          <div className="card"><h3>{I.check}Decision</h3>
            <div className="sub">Saved to the DA history after you confirm. {history.data?.length ? '' : 'No decision yet.'}</div>
            <div className="actions">
              <button className="btn green" onClick={() => setAsking('accept')}>{I.check}Accept</button>
              <button className="btn orange" onClick={() => setAsking('dispute')}>{I.deal}Dispute</button>
              <button className="btn red" onClick={() => setAsking('hold')}>{I.alert}Hold payment</button>
            </div>
            {(history.data ?? []).map((x, i) => (
              <div className="check" key={i}><span className={`pill ${DECISION[x.decision ?? '']?.[0] ?? 'muted'}`}>{DECISION[x.decision ?? '']?.[1] ?? x.decision}</span>
                <div><div className="n" style={{ textTransform: 'none' }}>{x.decided_by} · {when(x.decided_at)}</div>{x.note && <div className="e">{x.note}</div>}</div></div>
            ))}
          </div>
        </div>
        <div className="card viewer">
          <div className="row-gap" style={{ justifyContent: 'space-between', marginBottom: 12 }}><h3>{I.page}Documents</h3>
            <DocChips docs={documents} open={shown} onOpen={(file, page) => setOpen({ file, page })} /></div>
          <DocumentViewer docs={documents} open={shown} />
        </div>
      </div>
      {asking && <Confirm title={ask[asking][0]} text={ask[asking][1]} ok={ask[asking][2]} cls={ask[asking][3]} note onClose={(r) => void decide(r)} />}
      {toast.el}
    </>
  );
}
