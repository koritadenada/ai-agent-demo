// Port Assistant chat. Conversations are kept per user in Lakebase (the agents plugin's thread store), so the list
// on the left survives reloads and restarts; picking one continues it.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { useAgent } from '../lib/agent';
import { I } from '../lib/icons';
import { when } from '../lib/format';
import { Markdown } from '../lib/markdown';
import { Svc } from '../components/ui';

type Msg = { role: 'user' | 'assistant'; content: string; agents?: string[] };
type ThreadSummary = { id: string; updatedAt: string; messages: { content: string }[] };
type ThreadFull = { id: string; messages: { role: string; content: string }[] };

const LABELS: Record<string, string> = {
  ask_port_costs: 'Port costs and benchmarks', ask_da_audit: 'DA audit', ask_da_operations: 'DA operations',
  search_documents: 'Document search', port_call_timeline: 'Port call timeline',
};
const SAMPLES = ['Which ports have the highest cost per call?', 'Why are payments on hold?', 'Which open quotes are above the benchmark?',
  'What does the pilotage invoice of port call 20217 say?', 'How long does FDA approval take by port?', 'Give me the timeline of port call 20400'];

export function Assistant() {
  const agent = useAgent('port-assistant');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [input, setInput] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const asked = useRef(false);

  const loadThreads = useCallback(async () => {
    const r = await fetch('/api/agents/threads');
    if (r.ok) setThreads(((await r.json()) as { threads: ThreadSummary[] }).threads ?? []);
  }, []);
  useEffect(() => {
    let alive = true;
    fetch('/api/agents/threads').then((r) => (r.ok ? (r.json() as Promise<{ threads: ThreadSummary[] }>) : null))
      .then((d) => { if (alive && d) setThreads(d.threads ?? []); }).catch(() => undefined);
    return () => { alive = false; };
  }, []);
  useEffect(() => { box.current?.scrollTo({ top: 1e9 }); }, [messages, agent.text]);

  const ask = useCallback(async (q: string) => {
    if (!q.trim() || agent.streaming) return;
    setMessages((m) => [...m, { role: 'user', content: q }]);
    const thread = agent.threadId;
    const { answer, tools } = await agent.send(q, thread);
    const agents = [...new Set(tools.map((t) => LABELS[t]).filter(Boolean))];
    setMessages((m) => [...m, { role: 'assistant', content: answer || 'No answer.', agents }]);
    void loadThreads();
  }, [agent, loadThreads]);

  useEffect(() => {
    const q = (location.state as { question?: string } | null)?.question;
    if (q && !asked.current) { asked.current = true; queueMicrotask(() => void ask(q)); }
  }, [location.state, ask]);

  const open = async (id: string) => {
    const r = await fetch(`/api/agents/threads/${id}`);
    if (!r.ok) return;
    const t = (await r.json()) as ThreadFull;
    agent.reset();
    agent.setThreadId(t.id);
    setMessages(t.messages.filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content).map((m) => ({ role: m.role as Msg['role'], content: m.content })));
  };
  const remove = async (id: string) => {
    await fetch(`/api/agents/threads/${id}`, { method: 'DELETE' });
    if (agent.threadId === id) { agent.reset(); setMessages([]); }
    void loadThreads();
  };

  return (
    <>
      <div className="pagehead"><div><Svc name="Port Assistant" icon="assistant" /><h2>Ask the Port Assistant</h2>
        <p>Asks the right agent for each question: port costs, DA audit, DA operations, or the documents themselves. Answers use your own data permissions.</p></div>
        <button className="btn ghost sm" onClick={() => { agent.reset(); setMessages([]); }}>{I.plus}New conversation</button></div>
      <div className="chatgrid">
        <div className="card threads">
          <h3>{I.clock}Conversations</h3>
          {!threads.length && <div className="sub">Your conversations appear here.</div>}
          {threads.map((t) => (
            <div key={t.id} className={`thread${agent.threadId === t.id ? ' on' : ''}`} onClick={() => void open(t.id)}>
              <div className="tt">{t.messages[0]?.content}</div>
              <div className="s">{when(t.updatedAt)}</div>
              <button className="del" title="Delete" onClick={(e) => { e.stopPropagation(); void remove(t.id); }}>{I.trash}</button>
            </div>
          ))}
        </div>
        <div className="card chat">
          <div className="msgs" ref={box}>
            {!messages.length && (
              <div style={{ margin: 'auto', textAlign: 'center' }}>
                <div className="ico" style={{ margin: '0 auto 12px', width: 56, height: 56 }}>{I.assistant}</div><div className="t">What would you like to know?</div>
                <div className="suggest">{SAMPLES.map((q) => <button key={q} type="button" onClick={() => void ask(q)}>{q}</button>)}</div>
              </div>
            )}
            {messages.map((m, i) => (m.role === 'user'
              ? <div className="msg user" key={i}>{m.content}</div>
              : <div className="msg bot" key={i}><Markdown text={m.content} />
                  {!!m.agents?.length && <div className="via">Answered with {m.agents.map((a) => <span className="pill info" key={a}>{a}</span>)}</div>}</div>))}
            {agent.streaming && (
              <div className="msg bot">{agent.text ? <Markdown text={agent.text} /> : <span className="typing"><i /><i /><i /></span>}
                {!!agent.steps.length && <div className="via">Asking {[...new Set(agent.steps.map((x) => LABELS[x.name]).filter(Boolean))].map((a) => <span className="pill info" key={a}>{a}</span>)}</div>}</div>
            )}
            {agent.error && <div className="warn">{I.alert}{agent.error}</div>}
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); const q = input; setInput(''); void ask(q); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about costs, DAs, payments, port calls or documents" />
            <button className="btn" disabled={agent.streaming}>{I.send}Ask</button>
          </form>
        </div>
      </div>
    </>
  );
}
