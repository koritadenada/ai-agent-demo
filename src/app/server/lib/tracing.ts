// Agent traces, one MLflow experiment per agent (resources/<agent>.experiment.yml): every turn of an agent is a
// trace in that agent's experiment, stored as Delta tables in the agent's schema. A turn is the root of its trace,
// named after the agent, with the question as input, the answer as output, the conversation (session), the user and
// the prompt version it ran on. Inside it: a span per model call (messages, answer, tool calls, token usage), per tool
// call and per SQL query. The agents plugin traces to a single experiment only, so the app does this itself.
import { createWorkspaceClient, getCurrentUserId, getExecutionContext } from '@databricks/appkit';
import { DatabricksAdapter, type AgentAdapter, type AgentRunContext } from '@databricks/appkit/beta';
import { context, ROOT_CONTEXT, SpanStatusCode, trace, type Context } from '@opentelemetry/api';
import type { ReadableSpan, Span, SpanProcessor } from '@opentelemetry/sdk-trace-base';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import * as mlflow from '@mlflow/core';
import { DatabricksUCTableSpanExporter, DatabricksUCTableSpanProcessor } from '@mlflow/core/dist/exporters/uc_table.js';
import { agentExperiments, mlflowClient, type AgentId } from './agents';
import { promptRef } from './prompts';

type Client = ReturnType<typeof createWorkspaceClient>;
type Body = { messages?: unknown[]; tools?: { function?: { name?: string } }[] } & Record<string, unknown>;
type ToolCall = { id?: string; type: 'function'; function: { name: string; arguments: string } };

/**
 * Sends each trace to the experiment of the agent at its root; every other trace (HTTP requests, queries outside an
 * agent turn) is dropped.
 */
class AgentTraceRouter implements SpanProcessor {
  private agents = new Map<string, SpanProcessor>();
  private traces = new Map<string, SpanProcessor>();   // OTel trace id -> its agent's processor

  add(agent: string, processor: SpanProcessor): void {
    this.agents.set(agent, processor);
  }
  onStart(span: Span, parent: Context): void {
    const id = span.spanContext().traceId;
    if (!span.parentSpanContext?.spanId) {
      const agent = this.agents.get(span.name);
      if (!agent) return;
      this.traces.set(id, agent);
    }
    this.traces.get(id)?.onStart(span, parent);
  }
  onEnd(span: ReadableSpan): void {
    const id = span.spanContext().traceId;
    this.traces.get(id)?.onEnd(span);
    if (!span.parentSpanContext?.spanId) this.traces.delete(id);
  }
  async forceFlush(): Promise<void> {
    await Promise.all([...this.agents.values()].map((p) => p.forceFlush()));
  }
  async shutdown(): Promise<void> {
    await Promise.all([...this.agents.values()].map((p) => p.shutdown()));
  }
}

/** Installs the tracer provider (call before the app starts), then connects each agent to its experiment. */
export function startAgentTracing(): void {
  const router = new AgentTraceRouter();
  new NodeTracerProvider({ spanProcessors: [router] }).register();
  void agentExperiments().then((experiments) => {
    const client = mlflowClient();
    for (const [agent, e] of Object.entries(experiments)) {
      if (e.traces) router.add(agent, new DatabricksUCTableSpanProcessor(new DatabricksUCTableSpanExporter(client), e.traces));
      else console.warn(`[tracing] experiment ${e.experimentId} of ${agent} has no Unity Catalog trace location; not traced`);
    }
  }).catch((err: unknown) => console.warn(`[tracing] agent tracing off: ${(err as Error).message}`));
}

/** Collects what the model streamed back (OpenAI chat-completions chunks) for the span outputs. */
function collector() {
  const decoder = new TextDecoder();
  let buffer = '';
  let content = '';
  let finish: string | null = null;
  let usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | undefined;
  const calls = new Map<number, ToolCall>();
  const line = (raw: string) => {
    const data = raw.trim().startsWith('data: ') ? raw.trim().slice(6) : '';
    if (!data || data === '[DONE]') return;
    try {
      const chunk = JSON.parse(data) as {
        usage?: typeof usage;
        choices?: { delta?: { content?: unknown; tool_calls?: { index: number; id?: string; function?: { name?: string; arguments?: string } }[] }; finish_reason?: string | null }[];
      };
      if (chunk.usage) usage = chunk.usage;
      const choice = chunk.choices?.[0];
      if (choice?.finish_reason) finish = choice.finish_reason;
      const delta = choice?.delta;
      if (typeof delta?.content === 'string') content += delta.content;
      else if (Array.isArray(delta?.content)) {
        for (const part of delta.content as { type?: string; text?: string }[]) if (part.type === 'text' && part.text) content += part.text;
      }
      for (const tc of delta?.tool_calls ?? []) {
        const call = calls.get(tc.index) ?? { type: 'function', function: { name: '', arguments: '' } };
        if (tc.id) call.id = tc.id;
        if (tc.function?.name) call.function.name += tc.function.name;
        if (tc.function?.arguments) call.function.arguments += tc.function.arguments;
        calls.set(tc.index, call);
      }
    } catch {
      // not a JSON chunk (keep-alive or comment)
    }
  };
  return {
    push(bytes: Uint8Array) {
      buffer += decoder.decode(bytes, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      lines.forEach(line);
    },
    result() {
      line(buffer);
      const toolCalls = [...calls.values()];
      return {
        outputs: {
          choices: [{ index: 0, finish_reason: finish, message: { role: 'assistant', content, ...(toolCalls.length ? { tool_calls: toolCalls } : {}) } }],
          ...(usage ? { usage } : {}),
        },
        usage: usage && {
          input_tokens: usage.prompt_tokens ?? 0,
          output_tokens: usage.completion_tokens ?? 0,
          total_tokens: usage.total_tokens ?? (usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0),
        },
      };
    },
  };
}

/** Starts a CHAT_MODEL span under the active agent span; undefined outside an agent turn. */
function startModelSpan(endpoint: string, body: Body) {
  try {
    const parent = mlflow.getCurrentActiveSpan();
    if (!parent) return undefined;
    return mlflow.startSpan({
      name: endpoint,
      spanType: mlflow.SpanType.CHAT_MODEL,
      parent,
      inputs: { messages: body.messages, tools: body.tools },
      attributes: { 'mlflow.message.format': 'openai' },
    });
  } catch {
    return undefined;
  }
}

/** The serving endpoint as a streamBody, called with the caller's client (the signed-in user), each call traced. */
function servingStream(endpoint: string) {
  return async (request: unknown, signal?: AbortSignal): Promise<ReadableStream<Uint8Array>> => {
    const body = { ...(request as Body), stream: true };
    const span = startModelSpan(endpoint, body);
    try {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- typed in AppKit, unresolved by the linter
      const client: Client = getExecutionContext().client;
      const response = await client.request({
        method: 'POST',
        path: `/serving-endpoints/${encodeURIComponent(endpoint)}/invocations`,
        headers: new Headers({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
        body: JSON.stringify(body),
        signal,
      });
      if (!response.body) throw new Error('Response body is null: streaming not supported');
      if (!span) return response.body;
      const seen = collector();
      const finish = (status: mlflow.SpanStatusCode) => {
        const { outputs, usage } = seen.result();
        if (usage) span.setAttribute('mlflow.chat.tokenUsage', usage);
        span.end({ outputs, status });
      };
      return response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          seen.push(chunk);
          controller.enqueue(chunk);
        },
        flush: () => finish(mlflow.SpanStatusCode.OK),
        cancel: () => finish(mlflow.SpanStatusCode.ERROR),
      }));
    } catch (err) {
      span?.end({ outputs: { error: (err as Error).message }, status: mlflow.SpanStatusCode.ERROR });
      throw err;
    }
  };
}

/** Runs fn in the agent turn's trace context; tracing problems never break the agent. */
function inTurn(active: Context, fn: () => void): void {
  try {
    context.with(active, fn);
  } catch {
    // tracing off
  }
}

/**
 * An agent's model: the serving endpoint (as the signed-in user in an on-behalf-of-user run, like the plugin's
 * default adapter), with every turn traced to the agent's experiment.
 */
export function agentModel(agent: AgentId, endpoint = process.env.DATABRICKS_SERVING_ENDPOINT_NAME ?? ''): AgentAdapter {
  const adapter = new DatabricksAdapter({ streamBody: servingStream(endpoint) });
  const run = adapter.run.bind(adapter);
  adapter.run = async function* turn(input, ctx: AgentRunContext) {
    // the turn is the root of its own trace, not a child of the HTTP request
    const span = trace.getTracer('portcall-agents').startSpan(agent, {}, ROOT_CONTEXT);
    const active = trace.setSpan(ROOT_CONTEXT, span);
    span.setAttribute('mlflow.spanType', JSON.stringify(mlflow.SpanType.AGENT));
    const messages = input.messages.filter((m) => m.role !== 'system').map((m) => ({ role: m.role, content: m.content }));
    const question = [...messages].reverse().find((m) => m.role === 'user')?.content ?? '';
    const prompt = promptRef(agent);
    inTurn(active, () => {
      mlflow.getCurrentActiveSpan()?.setInputs({ messages });
      mlflow.updateCurrentTrace({
        requestPreview: question,
        sessionId: input.threadId,
        user: getCurrentUserId(),
        ...(prompt ? { tags: { 'mlflow.linkedPrompts': JSON.stringify([prompt]) } } : {}),
      });
    });
    const executeTool: AgentRunContext['executeTool'] = (name, args) => Promise.resolve(context.with(active, () => mlflow.withSpan(async (tool) => {
      const result = await ctx.executeTool(name, args);
      tool.setOutputs(result);
      return result;
    }, { name, spanType: mlflow.SpanType.TOOL, inputs: args })));
    const events = run(input, { ...ctx, executeTool });
    let answer = '';
    try {
      for (;;) {
        const next = await context.with(active, () => events.next());
        if (next.done) break;
        if (next.value.type === 'message_delta') answer += next.value.content;
        yield next.value;
      }
      span.setStatus({ code: SpanStatusCode.OK });
    } catch (err) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      throw err;
    } finally {
      inTurn(active, () => {
        mlflow.getCurrentActiveSpan()?.setOutputs({ role: 'assistant', content: answer });
        mlflow.updateCurrentTrace({ responsePreview: answer });
      });
      span.end();
    }
  };
  return adapter;
}
