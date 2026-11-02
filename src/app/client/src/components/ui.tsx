import { useState, type ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router';
import { I } from '../lib/icons';
import { DECISION, DOC, plural } from '../lib/format';
import { useConfig } from '../lib/config';

export function Shell() {
  const { user } = useConfig();
  const nav: [string, string][] = [['/', 'Overview'], ['/review', 'DA review'], ['/negotiator', 'Quote Negotiator'], ['/port-calls', 'Port calls'], ['/assistant', 'Port Assistant']];
  return (
    <>
      <header>
        <div className="bar">
          <NavLink to="/" className="brand">{I.mark}<div><b>PortCall</b><span>Agents</span></div></NavLink>
          <nav>{nav.map(([to, label]) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'on' : '')}>{label}</NavLink>)}</nav>
          <div className="who"><span>{user}</span><NavLink className="btn sm" to="/assistant">{I.assistant}Ask Port Assistant</NavLink></div>
        </div>
      </header>
      <main><Outlet /></main>
    </>
  );
}

export const Loading = ({ label = 'Loading' }: { label?: string }) => <div className="loading"><div className="spin" />{label}</div>;
export const Failed = ({ error }: { error: string }) => <div className="card"><h3>{I.alert}Something went wrong</h3><p className="muted">{error}</p></div>;
export const Svc = ({ name, icon }: { name: string; icon: keyof typeof I }) => <span className="svc">{I[icon]}{name}</span>;

export function DecisionPill({ decision }: { decision?: string | null }) {
  if (!decision) return <span className="pill info">To review</span>;
  const [cls, label] = DECISION[decision] ?? ['muted', decision];
  return <span className={`pill ${cls}`}>{label}</span>;
}

/** What the checks found on a final DA, the same on every screen. A count that is not there means not checked. */
export function LinesPill({ flagged, checked, ofTotal = false }: { flagged?: number | null; checked?: number | null; ofTotal?: boolean }) {
  if (flagged == null) return <span className="pill muted">Not checked yet</span>;
  if (!flagged) return <span className="pill ok">{ofTotal ? `All ${checked}` : 'All'} lines match</span>;
  return <span className="pill review">{ofTotal ? `${flagged} of ${checked} lines` : plural(flagged, 'line')} to check</span>;
}
export function PaymentPill({ hold }: { hold?: boolean | null }) {
  if (hold == null) return <span className="pill muted">Not checked yet</span>;
  return hold ? <span className="pill hold">Payment on hold</span> : <span className="pill ok">Bank details match</span>;
}

export type Doc = { file_item_id: number; doc_type: string; volume_path: string };

/** The PDFs of a DA, read as the user through the files plugin; opens on the page asked for. */
export function DocumentViewer({ docs, open }: { docs: Doc[]; open: { file: number; page: number } | null }) {
  const doc = open ? docs.find((d) => d.file_item_id === open.file) : null;
  return doc ? (
    <iframe title="Document" key={`${doc.file_item_id}-${open?.page}`}
      src={`/api/files/files/raw?path=${encodeURIComponent(doc.volume_path)}#page=${open?.page ?? 1}&view=FitH`} />
  ) : <div className="empty">No document to show</div>;
}

export function PageChip({ page, on, onClick, label }: { page?: number; on?: boolean; onClick: () => void; label?: string }) {
  return <span className={`pagechip${on ? ' on' : ''}`} onClick={onClick}>{label ? null : I.page}{label ?? `p. ${page}`}</span>;
}

export function DocChips({ docs, open, onOpen }: { docs: Doc[]; open: { file: number; page: number } | null; onOpen: (file: number, page: number) => void }) {
  return <div className="row-gap">{docs.map((d) => (
    <PageChip key={d.file_item_id} label={DOC[d.doc_type] ?? d.doc_type} on={open?.file === d.file_item_id && open.page === 1} onClick={() => onOpen(d.file_item_id, 1)} />
  ))}</div>;
}

export function Confirm({ title, text, ok, cls = '', note = false, onClose }: {
  title: string; text: ReactNode; ok: string; cls?: string; note?: boolean; onClose: (result: { note: string } | null) => void;
}) {
  const [value, setValue] = useState('');
  return (
    <div className="modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(null); }}>
      <div className="box">
        <h3>{title}</h3><p>{text}</p>
        {note && <div className="field"><label>Note for the agent and the team (optional)</label><textarea rows={3} value={value} onChange={(e) => setValue(e.target.value)} /></div>}
        <div className="actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn ghost" onClick={() => onClose(null)}>Cancel</button>
          <button className={`btn ${cls}`} autoFocus onClick={() => onClose({ note: value })}>{ok}</button>
        </div>
      </div>
    </div>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<{ text: string; err: boolean } | null>(null);
  const show = (text: string, err = false) => { setMsg({ text, err }); setTimeout(() => setMsg(null), 3500); };
  const el = msg ? <div className={`toast${msg.err ? ' err' : ''}`}>{msg.text}</div> : null;
  return { show, el };
}

export async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = (await r.json().catch(() => ({}))) as T & { error?: string };
  if (!r.ok) throw new Error(data.error ?? r.statusText);
  return data;
}
