// Port calls (Timeline Summarizer): the statement of facts timeline and a written account on demand.
import { useState } from 'react';
import { Link } from 'react-router';
import { useParams } from 'react-router';
import { useQuery as useAnalyticsQuery } from '../lib/query';
import { sql } from '@databricks/appkit-ui/js';
import { useSchemas } from '../lib/config';
import { useAgent } from '../lib/agent';
import { I } from '../lib/icons';
import { month, num, plural, when } from '../lib/format';
import { DocChips, DocumentViewer, Failed, Loading, PageChip, Svc, type Doc } from '../components/ui';
import { toHtml } from '../lib/markdown';

export function PortCalls() {
  const s = useSchemas();
  const { data, loading, error } = useAnalyticsQuery('port_calls', { gold: s.gold, silver: s.silver });
  if (error) return <Failed error={error} />;
  return (
    <>
      <div className="pagehead"><div><Svc name="Timeline Summarizer" icon="clock" /><h2>Port calls</h2>
        <p>Port calls with a statement of facts: the timeline read from the document, and a written account on demand.</p></div></div>
      {loading ? <Loading /> : (
        <div className="grid g3">{(data ?? []).map((r) => {
          const facts = [r.port_stay_hours != null && `${num(r.port_stay_hours, 1)} h in port`, r.events && plural(r.events, 'event')].filter(Boolean).join(' · ');
          return (
            <Link className="card pcard" key={r.port_call_id} to={`/port-calls/${r.port_call_id}`}>
              <div className="row-gap"><div className="ico">{I.ship}</div><div><div className="t">{r.vessel_name}</div><div className="s">{r.port_name} · {month(r.call_month)}</div></div></div>
              <div className="s">{r.agent_name}<br />{r.longest_wait_hours == null ? 'No timed events read'
                : `Longest wait ${num(r.longest_wait_hours, 1)} h: ${String(r.wait_from).toLowerCase()} to ${String(r.wait_to).toLowerCase()}`}</div>
              <div className="foot"><span className="s">Port call {r.port_call_id}</span>{facts && <span className="pill muted">{facts}</span>}</div>
            </Link>
          );
        })}</div>
      )}
    </>
  );
}

export function PortCall() {
  const id = Number(useParams().id);
  const s = useSchemas();
  const pc = useAnalyticsQuery('port_call', { gold: s.gold, port_call_id: sql.bigint(id) });
  const events = useAnalyticsQuery('port_call_events', { gold: s.gold, silver: s.silver, port_call_id: sql.bigint(id) });
  const p = pc.data?.[0];
  const docs = useAnalyticsQuery('documents', { gold: s.gold, silver: s.silver, evaluation_id: sql.bigint(0), port_call_id: sql.bigint(id) });
  const story = useAgent('timeline-summarizer');
  const [open, setOpen] = useState<{ file: number; page: number } | null>(null);
  if (pc.error) return <Failed error={pc.error} />;
  if (!p) return pc.loading ? <Loading /> : <div className="card">No such port call.</div>;
  const documents = (docs.data ?? []) as Doc[];
  const sof = documents.find((d) => d.doc_type === 'statement_of_facts');
  const shown = open ?? (sof ? { file: sof.file_item_id, page: 1 } : null);
  const ev = events.data ?? [];
  // page citations in the written account become chips that open the statement of facts on that page
  const storyHtml = toHtml(story.text).replace(/\(p\. (\d+)\)/g, (_m, n: string) => `<span class="pagechip" data-page="${n}">p. ${n}</span>`);

  return (
    <>
      <Link className="back" to="/port-calls">{I.back}All port calls</Link>
      <div className="pagehead"><div><h2>{p.vessel_name} at {p.port_name}</h2>
        <p>{p.vessel_type}, {num(p.gross_tonnage, 0)} GT · IMO {p.imo} · {p.agent_name} for {p.buyer_name}</p></div>
        {p.evaluation_id && <Link className="btn ghost sm" to={`/review/${p.evaluation_id}`}>{I.review}Final DA</Link>}</div>
      <div className="card" style={{ marginBottom: 20 }}><div className="facts">
        <div className="fact"><div className="k">Arrival</div><div className="v">{when(p.schedule_date_in)}</div></div>
        <div className="fact"><div className="k">Departure</div><div className="v">{when(p.schedule_date_out)}</div></div>
        <div className="fact"><div className="k">Port stay</div><div className="v">{num(p.port_stay_hours, 1)} h</div></div>
        <div className="fact"><div className="k">Quoted</div><div className="v">{num(p.quoted_amount)} <span className="muted small">{p.currency}</span></div></div>
        <div className="fact"><div className="k">Final</div><div className="v">{num(p.final_amount)} <span className="muted small">{p.currency}</span></div></div>
        <div className="fact"><div className="k">FDA to approval</div><div className="v">{p.fda_approval_hours != null ? `${num(p.fda_approval_hours, 1)} h` : '-'}</div></div>
      </div></div>
      <div className="grid g-main">
        <div className="grid">
          <div className="card">
            <div className="row-gap" style={{ justifyContent: 'space-between' }}><h3>{I.clock}Timeline from the statement of facts</h3><Svc name="Timeline Summarizer" icon="clock" /></div>
            <div className="sub">{ev.length ? `${ev.length} events read from the document; click a page to see it.` : 'No statement of facts read yet.'}</div>
            <div className="timeline">{ev.map((e, i) => {
              const prev = ev[i - 1];
              const h = prev?.event_time && e.event_time ? (new Date(e.event_time).getTime() - new Date(prev.event_time).getTime()) / 36e5 : null;
              const gap = h == null ? null : /^commenced/i.test(prev?.event ?? '') ? <div className="gap ops">{num(h, 1)} hours of operations</div>
                : h >= 3 ? <div className="gap">waited {num(h, 1)} hours</div> : null;
              return (
                <div key={e.event_order}>{gap}
                  <div className="ev"><div className="time">{e.event_time ? when(e.event_time) : e.event_time_text}</div><div className="what">{e.event}</div>
                    <PageChip page={e.page_number ?? 1} onClick={() => e.file_item_id && setOpen({ file: e.file_item_id, page: e.page_number ?? 1 })} /></div>
                </div>
              );
            })}</div>
          </div>
          <div className="card"><h3>{I.spark}Written account</h3><div className="sub">Written on demand from the events above, with the page of each one.</div>
            {story.text ? (
              <div className="story" onClick={(e) => {
                const page = (e.target as HTMLElement).dataset.page;
                if (page && sof) setOpen({ file: sof.file_item_id, page: Number(page) });
              }}
              // eslint-disable-next-line react/no-danger -- escaped markdown, our own chips
              dangerouslySetInnerHTML={{ __html: storyHtml }} />
            ) : story.streaming ? <Loading label="Writing the account" /> : (
              <button className="btn" disabled={!ev.length} onClick={() => void story.send(`Write the account of port call ${id}.`)}>{I.spark}Write the account</button>
            )}
            {story.error && <div className="warn" style={{ marginTop: 12 }}>{I.alert}{story.error}</div>}
          </div>
        </div>
        <div className="card viewer">
          <div className="row-gap" style={{ justifyContent: 'space-between', marginBottom: 12 }}><h3>{I.page}Documents</h3>
            <DocChips docs={documents} open={shown} onOpen={(file, page) => setOpen({ file, page })} /></div>
          <DocumentViewer docs={documents} open={shown} />
        </div>
      </div>
    </>
  );
}
