// One hook for every agent screen, on AppKit's SSE client and the agents plugin's /api/agents/chat. Unlike
// useAgentChat it can continue a saved thread (threadId), which the chat history needs.
import { useCallback, useRef, useState } from 'react';
import { connectSSE } from '@databricks/appkit-ui/js';

export type ToolStep = { id: string; name: string; args: Record<string, unknown>; output?: unknown; done: boolean };
type Event = {
  type: string;
  delta?: string;
  data?: { threadId?: string };
  error?: string;
  item?: { type?: string; id?: string; call_id?: string; name?: string; arguments?: string; output?: string };
};

const parse = (s?: string) => {
  try { return s ? (JSON.parse(s) as unknown) : undefined; } catch { return s; }
};

export function useAgent(agent: string) {
  const [text, setText] = useState('');
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const send = useCallback(async (message: string, thread?: string | null) => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setText(''); setSteps([]); setError(null); setStreaming(true);
    let answer = '';
    let failed: string | null = null;
    const used: string[] = [];
    await connectSSE({
      url: '/api/agents/chat',
      payload: { agent, message, ...(thread ? { threadId: thread } : {}) },
      signal: ctrl.signal,
      maxRetries: 0,
      timeout: 600_000,
      onError: (e) => { failed = e instanceof Error ? e.message : String(e); },
      onMessage: (m) => {
        const e = parse(m.data) as Event | undefined;
        if (!e || typeof e !== 'object') return Promise.resolve();
        if (e.type === 'appkit.metadata' && e.data?.threadId) setThreadId(e.data.threadId);
        else if (e.type === 'response.output_text.delta' && e.delta) { answer += e.delta; setText(answer); }
        else if (e.type === 'response.output_item.added' && e.item?.type === 'function_call') {
          const step = { id: e.item.call_id ?? e.item.id ?? String(Math.random()), name: e.item.name ?? '', args: (parse(e.item.arguments) as Record<string, unknown>) ?? {}, done: false };
          used.push(step.name);
          setSteps((s) => [...s, step]);
        } else if (e.type === 'response.output_item.done' && e.item?.type === 'function_call_output') {
          const id = e.item.call_id ?? e.item.id;
          setSteps((s) => s.map((x) => (x.id === id ? { ...x, output: parse(e.item?.output), done: true } : x)));
        } else if (e.type === 'error' || e.type === 'response.failed') failed = e.error ?? failed ?? 'The agent stopped';
        return Promise.resolve();
      },
    });
    setStreaming(false);
    if (failed) setError(failed);
    return { answer, tools: used };
  }, [agent]);

  const reset = useCallback(() => {
    abort.current?.abort();
    setText(''); setSteps([]); setThreadId(null); setError(null); setStreaming(false);
  }, []);

  return { text, steps, threadId, setThreadId, streaming, error, send, reset };
}
