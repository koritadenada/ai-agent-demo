// SQL for the agent tools. The agents run on behalf of the user, so analytics.query executes with the user's
// token: Unity Catalog decides what each tool can read.
import { sql } from '@databricks/appkit';

export type Analytics = { query: (q: string, p?: Record<string, ReturnType<typeof sql.string>>) => Promise<unknown> };

export async function rows(analytics: Analytics, q: string, params: Record<string, string | number | null | undefined> = {}) {
  const bound = Object.fromEntries(
    Object.entries(params).map(([k, v]) => [k, typeof v === 'number' ? sql.bigint(v) : sql.string(v ?? '')]),
  );
  const result = await analytics.query(q, bound as Record<string, ReturnType<typeof sql.string>>);
  return Array.isArray(result) ? (result as Record<string, unknown>[]) : ((result as { data?: Record<string, unknown>[] })?.data ?? []);
}
