// Chat history in Lakebase: the agents plugin's ThreadStore, so a conversation with the Port Assistant survives a
// reload or a restart and each user sees only their own threads. Written as the app's service principal, keyed by
// the user id (the plugin passes it on every call).
import type { Message, Thread, ThreadStore } from '@databricks/appkit/beta';
import { randomUUID } from 'node:crypto';

type Query = (text: string, params?: unknown[]) => Promise<{ rows: Record<string, unknown>[] }>;

const SCHEMA_SQL = [
  'CREATE SCHEMA IF NOT EXISTS chat',
  `CREATE TABLE IF NOT EXISTS chat.threads (
     id UUID PRIMARY KEY, user_id TEXT NOT NULL, title TEXT,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())`,
  'CREATE INDEX IF NOT EXISTS threads_by_user ON chat.threads (user_id, updated_at DESC)',
  `CREATE TABLE IF NOT EXISTS chat.messages (
     id TEXT PRIMARY KEY, thread_id UUID NOT NULL REFERENCES chat.threads (id) ON DELETE CASCADE,
     role TEXT NOT NULL, content TEXT NOT NULL, tool_call_id TEXT, tool_calls JSONB,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now())`,
  'CREATE INDEX IF NOT EXISTS messages_by_thread ON chat.messages (thread_id, created_at)',
];

export class LakebaseThreadStore implements ThreadStore {
  private query: Query | null = null;
  // The agents plugin keeps the Thread it got from create/get and reads its messages after addMessage (the
  // in-memory store mutates that object), so the threads in use are kept here and updated along with Lakebase.
  private live = new Map<string, Thread>();

  private track(thread: Thread): Thread {
    this.live.delete(thread.id);
    this.live.set(thread.id, thread);
    if (this.live.size > 500) this.live.delete(this.live.keys().next().value as string);
    return thread;
  }

  /** Called once Lakebase is ready (onPluginsReady); creates the tables when missing. */
  async attach(query: Query): Promise<void> {
    const { rows } = await query(
      "SELECT 1 FROM information_schema.tables WHERE table_schema = 'chat' AND table_name IN ('threads', 'messages')",
    );
    if (rows.length < 2) for (const statement of SCHEMA_SQL) await query(statement);
    this.query = query;
  }

  private db(): Query {
    if (!this.query) throw new Error('Chat history is not ready yet');
    return this.query;
  }

  async create(userId: string): Promise<Thread> {
    const id = randomUUID();
    const { rows } = await this.db()('INSERT INTO chat.threads (id, user_id) VALUES ($1, $2) RETURNING created_at, updated_at', [id, userId]);
    return this.track({ id, userId, messages: [], createdAt: new Date(rows[0].created_at as string), updatedAt: new Date(rows[0].updated_at as string) });
  }

  async get(threadId: string, userId: string): Promise<Thread | null> {
    const { rows } = await this.db()('SELECT id, user_id, created_at, updated_at FROM chat.threads WHERE id = $1 AND user_id = $2', [threadId, userId]);
    if (!rows.length) return null;
    const messages = await this.db()(
      'SELECT id, role, content, tool_call_id, tool_calls, created_at FROM chat.messages WHERE thread_id = $1 ORDER BY created_at, id',
      [threadId],
    );
    return this.track({
      id: threadId, userId,
      createdAt: new Date(rows[0].created_at as string), updatedAt: new Date(rows[0].updated_at as string),
      messages: messages.rows.map((m) => ({
        id: m.id as string, role: m.role as Message['role'], content: m.content as string,
        toolCallId: (m.tool_call_id as string) ?? undefined, toolCalls: (m.tool_calls as Message['toolCalls']) ?? undefined,
        createdAt: new Date(m.created_at as string),
      })),
    });
  }

  async list(userId: string): Promise<Thread[]> {
    const { rows } = await this.db()(
      'SELECT id, title, created_at, updated_at FROM chat.threads WHERE user_id = $1 AND title IS NOT NULL ORDER BY updated_at DESC LIMIT 50',
      [userId],
    );
    // Titles stand in for the messages in a list: the first user question of each thread.
    return rows.map((r) => ({
      id: r.id as string, userId, createdAt: new Date(r.created_at as string), updatedAt: new Date(r.updated_at as string),
      messages: [{ id: `${r.id as string}-title`, role: 'user', content: r.title as string, createdAt: new Date(r.created_at as string) }],
    }));
  }

  async addMessage(threadId: string, userId: string, message: Message): Promise<void> {
    const owner = await this.db()('SELECT 1 FROM chat.threads WHERE id = $1 AND user_id = $2', [threadId, userId]);
    if (!owner.rows.length) throw new Error('Thread not found');
    await this.db()(
      `INSERT INTO chat.messages (id, thread_id, role, content, tool_call_id, tool_calls, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (id) DO NOTHING`,
      [message.id || randomUUID(), threadId, message.role, message.content ?? '', message.toolCallId ?? null,
       message.toolCalls ? JSON.stringify(message.toolCalls) : null, message.createdAt ?? new Date()],
    );
    const thread = this.live.get(threadId);
    if (thread && !thread.messages.some((m) => m.id === message.id)) {
      thread.messages.push(message);
      thread.updatedAt = new Date();
    }
    await this.db()(
      `UPDATE chat.threads SET updated_at = now(),
         title = COALESCE(title, CASE WHEN $2 = 'user' THEN left($3, 120) END) WHERE id = $1`,
      [threadId, message.role, message.content ?? ''],
    );
  }

  async delete(threadId: string, userId: string): Promise<boolean> {
    const { rows } = await this.db()('DELETE FROM chat.threads WHERE id = $1 AND user_id = $2 RETURNING id', [threadId, userId]);
    this.live.delete(threadId);
    return rows.length > 0;
  }
}
