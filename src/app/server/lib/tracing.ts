// Agent traces (MLflow experiment portcall-agent-traces, Delta tables in the app schema). The agents plugin opens an
// AGENT span per turn and a TOOL span per tool call; this adds the rest:
//   - each turn is its own trace, named after the agent, with the question as input and the answer as output
//     (otherwise the HTTP request is the root and the trace is exported before the agent span ends)
//   - each model call is a CHAT_MODEL span with the messages, the answer, the tool calls and the token usage
//   - the trace carries the conversation (session) and the user, for the Sessions view
import { createWorkspaceClient, getCurrentUserId, getExecutionContext } from '@databricks/appkit';
import { DatabricksAdapter, type AgentAdapter } from '@databricks/appkit/beta';
import { context, ROOT_CONTEXT } from '@opentelemetry/api';
import * as mlflow from '@mlflow/core';
import type { Application, NextFunction, Request, Response } from 'express';

type Client = ReturnType<typeof createWorkspaceClient>;
type Body = { messages?: unknown[]; tools?: { function?: { name?: string } }[] } & Record<string, unknown>;
type ToolCall = { id?: string; type: 'function'; function: { name: string; arguments: string } };

/**
 * Runs agent chat requests outside the HTTP request span, so the agent span is the root of its trace. Plugin routes
 * are mounted before server extensions, so the middleware is moved to the front of the stack.
 */
export function agentTurnsAsTraces(app: Application): void {
  app.use('/api/agents/chat', (_req: Request, _res: Response, next: NextFunction) => context.with(ROOT_CONTEXT, next));
  const router: unknown = Reflect.get(app, '_router');  // Express 4
  const stack: unknown = router && Reflect.get(router as object, 'stack');
  if (!Array.isArray(stack)) return;
  // right after Express's own init layers, before every plugin route
  const init = stack.findIndex((layer: unknown) => Reflect.get(layer as object, 'name') === 'expressInit');
  stack.splice(init + 1, 0, stack.pop());
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

/** Starts a CHAT_MODEL span under the active agent span; undefined when tracing is off. */
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

/**
 * The agents' model: the serving endpoint, called with the caller's client (the signed-in user in an
 * on-behalf-of-user run, as the plugin's default adapter does), with every call traced.
 */
export function tracedModel(endpoint = process.env.DATABRICKS_SERVING_ENDPOINT_NAME ?? ''): AgentAdapter {
  const adapter = new DatabricksAdapter({
    async streamBody(request, signal) {
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
    },
  });
  // the conversation and the user on the trace, set once per turn from inside the agent span
  const run = adapter.run.bind(adapter);
  adapter.run = (input, ctx) => {
    try {
      mlflow.updateCurrentTrace({ sessionId: input.threadId, user: getCurrentUserId() });
    } catch {
      // tracing off
    }
    return run(input, ctx);
  };
  return adapter;
}
