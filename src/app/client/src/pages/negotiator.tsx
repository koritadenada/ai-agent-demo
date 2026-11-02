// Quote Negotiator: open quotes against the benchmark, and the agent that drafts the email.
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { useQuery as useAnalyticsQuery } from '../lib/query';
import { sql } from '@databricks/appkit-ui/js';
import { useSchemas } from '../lib/config';
import { useAgent } from '../lib/agent';
import { I } from '../lib/icons';
import { month, num, when } from '../lib/format';
import { Confirm, Failed, Loading, Svc, post, useToast } from '../components/ui';

export function Quotes() {
  const s = useSchemas();
  const nav = useNavigate();
  const { data, loading, error } = useAnalyticsQuery('quotes', { gold: s.gold, app: s.app });
  if (error) return <Failed error={error} />;
  return (
    <>
      <div className="pagehead"><div><Svc name="Quote Negotiator" icon="deal" /><h2>Open quotes</h2>
        <p>PDA quotes not yet approved, against what each port usually costs for the same vessel type and size.</p></div></div>
      {loading ? <Loading /> : (
        <div className="tbl"><table><tbody>
          <tr><th>Vessel and port</th><th>Agent</th><th>Call</th><th className="num">Quoted</th><th>Above benchmark</th><th className="num">Potential saving</th><th /></tr>
          {(data ?? []).map((q) => (
            <tr className="row" key={q.proforma_id} onClick={() => void nav(`/negotiator/${q.proforma_id}`)}>
              <td><b>{q.vessel_name}</b><div className="exp">{q.port_name} · {q.vessel_type}, {q.size_band}</div></td>
              <td>{q.agent_name}<div className="exp">{q.buyer_name}</div></td>
              <td className="nowrap">{month(q.call_month)}</td>
              <td className="num nowrap">{num(q.quoted_eur)} <span className="muted small">EUR</span></td>
              <td>{q.flagged_lines ? <span className="pill review">{q.flagged_lines} of {q.lines} lines</span> : <span className="pill ok">None</span>}</td>
              <td className="num nowrap amt-ok">{q.saving_eur ? `${num(q.saving_eur)} EUR` : ''}</td>
              <td>{q.has_draft && <span className="pill info">Draft saved</span>}</td>
            </tr>
          ))}
        </tbody></table></div>
      )}
    </>
  );
}

type DraftArgs = { subject: string; body: string; lines: unknown[] };
const STEP_LABEL: Record<string, (a: Record<string, unknown>) => string> = {
  get_quote: () => 'Read the quote',
  get_price_history: (a) => `Price history: ${String(a.expense_category)} at ${String(a.port_name)}`,
  get_competing_quotes: (a) => `Competing quotes: ${String(a.expense_category)} at ${String(a.port_name)}`,
  submit_draft: () => 'Checked every amount against the data',
};

export function QuoteDetail() {
  const id = Number(useParams().id);
  const [version, setVersion] = useState(0);
  return <QuoteBody key={version} id={id} onSaved={() => setVersion((v) => v + 1)} />;
}

function QuoteBody({ id, onSaved }: { id: number; onSaved: () => void }) {
  const s = useSchemas();
  const toast = useToast();
  const lines = useAnalyticsQuery('quote_lines', { gold: s.gold, proforma_id: sql.bigint(id) });
  const drafts = useAnalyticsQuery('quote_drafts', { app: s.app, proforma_id: sql.bigint(id) });
  const agent = useAgent('quote-negotiator');
  const [instructions, setInstructions] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [confirming, setConfirming] = useState(false);
  if (lines.error) return <Failed error={lines.error} />;
  if (!lines.data) return <Loading />;
  const q = lines.data[0];
  if (!q) return <div className="card">No such open quote.</div>;
  const submit = agent.steps.find((x) => x.name === 'submit_draft');
  const draft = submit?.args as DraftArgs | undefined;
  const unverified = ((submit?.output as { unverified_amounts?: string[] } | undefined)?.unverified_amounts) ?? [];

  const run = async () => {
    setSubject(''); setBody('');
    await agent.send(`Draft the negotiation email for the open PDA quote ${id}.${instructions.trim() ? ` Analyst instructions: ${instructions.trim()}` : ''}`);
  };
  const shownSubject = subject || draft?.subject || '';
  const shownBody = body || draft?.body || '';
  const save = async (ok: { note: string } | null) => {
    setConfirming(false);
    if (!ok || !draft) return;
    try {
      await post(`/api/quotes/${id}/drafts`, { subject: shownSubject, body: shownBody, lines: draft.lines, unverified_amounts: unverified });
      toast.show('Draft saved'); onSaved();
    } catch (e) { toast.show((e as Error).message, true); }
  };

  return (
    <>
      <Link className="back" to="/negotiator">{I.back}All open quotes</Link>
      <div className="pagehead"><div><h2>{q.vessel_name} at {q.port_name}</h2>
        <p>PDA quote from {q.agent_name} for {q.buyer_name} · {q.vessel_type}, {q.size_band} · {month(q.call_month)}</p></div>
        <span className="pill info">Open quote</span></div>
      <div className="grid g-main">
        <div className="card flush">
          <div className="head"><h3>{I.euro}Quote against the benchmark</h3>
            <div className="sub" style={{ margin: 0 }}>Benchmark: the median final cost of past calls, same port, vessel type and size first. Amounts in EUR.</div></div>
          <div className="tbl" style={{ borderRadius: 0, borderLeft: 0, borderRight: 0, borderBottom: 0 }}><table><tbody>
            <tr><th>Expense</th><th className="num">Quoted</th><th className="num">Benchmark</th><th className="num">Gap</th><th className="num">Saving</th></tr>
            {lines.data.map((l, i) => (
              <tr key={i}><td><b>{l.expense_name}</b>{l.flagged && <div className="exp">{l.reasoning}</div>}</td>
                <td className={`num nowrap ${l.flagged ? 'amt-review' : ''}`}>{num(l.quoted_amount_eur)}</td>
                <td className="num nowrap">{l.benchmark_median_eur != null ? num(l.benchmark_median_eur) : <span className="muted small">too few calls</span>}
                  {l.benchmark_sample_size ? <div className="exp">{l.benchmark_sample_size} past calls</div> : null}</td>
                <td className="num nowrap">{l.gap_to_benchmark_pct != null && <span className={`pill ${l.flagged ? 'review' : 'ok'}`}>{l.gap_to_benchmark_pct > 0 ? '+' : ''}{num(l.gap_to_benchmark_pct, 1)}%</span>}</td>
                <td className="num nowrap amt-ok">{l.flagged ? num(l.potential_saving_eur) : ''}</td></tr>
            ))}
            <tr className="total"><td>Total</td><td className="num">{num(lines.data.reduce((a, l) => a + Number(l.quoted_amount_eur ?? 0), 0))}</td><td /><td />
              <td className="num">{num(lines.data.filter((l) => l.flagged).reduce((a, l) => a + Number(l.potential_saving_eur ?? 0), 0))}</td></tr>
          </tbody></table></div>
        </div>
        <div className="grid">
          <div className="card">
            <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.deal}Negotiation email</h3><Svc name="Quote Negotiator" icon="deal" /></div>
            <div className="sub">The agent reads the quote, the price history at this port and past competing quotes, then drafts the email. Every amount is checked against the data.</div>
            <div className="field"><label>Your instructions (optional)</label>
              <input type="text" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="For example: keep it short, focus on pilotage and towage" /></div>
            <button className="btn" disabled={agent.streaming} onClick={() => void run()}>{I.spark}{agent.steps.length ? 'Draft again' : 'Draft the email'}</button>
            {(agent.streaming || agent.steps.length > 0) && (
              <div className="steps">{agent.steps.map((x) => (
                <div className="step" key={x.id}>{x.done ? I.check : <span className="spin" style={{ width: 14, height: 14 }} />}{(STEP_LABEL[x.name] ?? (() => x.name))(x.args)}</div>
              ))}{agent.streaming && !agent.steps.length && <Loading label="Reading the quote, the price history and competing quotes" />}</div>
            )}
            {agent.error && <div className="warn" style={{ marginTop: 14 }}>{I.alert}{agent.error}</div>}
            {draft && submit?.done && (
              <>
                {unverified.length
                  ? <div className="warn">{I.alert}<div><b>Check these amounts:</b> {unverified.join(', ')} were not found in the data the agent read.</div></div>
                  : <div className="ok-note">{I.check}Every amount in the email was found in the data.</div>}
                <div className="field" style={{ marginTop: 14 }}><label>Subject</label><input type="text" value={shownSubject} onChange={(e) => setSubject(e.target.value)} /></div>
                <div className="field"><label>Email</label><textarea rows={16} value={shownBody} onChange={(e) => setBody(e.target.value)} /></div>
                <div className="actions">
                  <button className="btn" onClick={() => setConfirming(true)}>{I.save}Save draft</button>
                  <button className="btn ghost" onClick={() => { void navigator.clipboard.writeText(`${shownSubject}\n\n${shownBody}`); toast.show('Copied'); }}>{I.copy}Copy</button>
                </div>
              </>
            )}
          </div>
          {!!drafts.data?.length && (
            <div className="card"><h3>{I.save}Saved drafts</h3>{drafts.data.map((d, i) => (
              <div className="check" key={i}><span className="pill info">Draft</span><div><div className="n" style={{ textTransform: 'none' }}>{d.subject}</div><div className="e">{d.created_by} · {when(d.created_at)}</div></div></div>
            ))}</div>
          )}
        </div>
      </div>
      {confirming && <Confirm title="Save this draft" text="The draft is saved with the quote so the team can send it. Nothing is sent to the agent." ok="Save draft" onClose={(r) => void save(r)} />}
      {toast.el}
    </>
  );
}
