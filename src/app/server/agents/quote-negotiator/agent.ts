// Quote Negotiator: drafts a citation-backed negotiation email for an open PDA quote. The model reads the quote, the
// price history and competing quotes through tools (SQL on gold, as the signed-in user); the benchmark math stays in
// SQL. submit_draft checks every amount in the email against the same data and reports any it cannot find, so the
// analyst sees them before saving. One-shot (ephemeral); prompt from the registry (negotiator).
import { createAgent, tool } from '@databricks/appkit/beta';
import { z } from 'zod';
import { GOLD } from '../../lib/config';
import { rows } from '../../lib/sql';
import { fromRegistry } from '../../lib/prompts';
import { agentModel } from '../../lib/tracing';
import { analyticsOf } from '../../lib/tools';
import type { Analytics } from '../../lib/sql';

const quoteSql = `
  SELECT c.port_call_id, c.proforma_id, c.port_name, c.vessel_name, c.vessel_type, c.size_band, c.agent_name,
         c.buyer_name, CAST(c.call_month AS STRING) AS call_month, q.expense_name, q.expense_category, q.currency,
         ROUND(q.quoted_amount, 2) AS quoted_amount, q.quoted_amount_eur, ROUND(q.benchmark_median_eur, 2) AS benchmark_median_eur,
         q.benchmark_level, q.benchmark_sample_size, q.local_port_min_eur, ROUND(q.region_min_median_eur, 2) AS region_min_median_eur,
         ROUND(q.gap_to_benchmark_pct, 1) AS gap_to_benchmark_pct, q.flagged, ROUND(q.potential_saving_eur, 2) AS potential_saving_eur, q.reasoning
  FROM ${GOLD}.quote_benchmark_flags q JOIN ${GOLD}.port_call_costs c ON c.proforma_id = q.proforma_id
  WHERE q.proforma_id = :p ORDER BY q.flagged DESC, q.potential_saving_eur DESC`;
const historySql = `
  SELECT CAST(r.call_month AS STRING) AS call_month, r.vessel_name, r.vessel_type, r.size_band, r.final_amount_eur, r.port_call_id
  FROM ${GOLD}.expense_reconciliation r JOIN ${GOLD}.port_call_costs c ON c.evaluation_id = r.evaluation_id
  WHERE r.port_name = :port AND r.expense_category = :cat AND c.evaluation_state IN ('APPROVED', 'PAID')
  ORDER BY r.call_month DESC, r.port_call_id DESC LIMIT 8`;
const competingSql = `
  SELECT CAST(call_month AS STRING) AS call_month, vessel_type, size_band, quotes_received, lowest_amount_eur,
         accepted_amount_eur, highest_amount_eur
  FROM ${GOLD}.rfq_comparison WHERE port_name = :port AND expense_category = :cat AND quotes_received > 1
  ORDER BY call_month DESC LIMIT 5`;

const money = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Every amount the tools could have returned for this quote, written as 1,234.56. */
async function knownAmounts(analytics: Analytics, proformaId: number): Promise<Set<string>> {
  const lines = await rows(analytics, quoteSql, { p: proformaId });
  const found = new Set<string>();
  const add = (o: Record<string, unknown>) => {
    for (const v of Object.values(o)) {
      const n = typeof v === 'number' ? v : typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v) ? Number(v) : NaN;
      if (Number.isFinite(n)) found.add(money(n));
      if (typeof v === 'string') for (const m of v.match(/\d{1,3}(?:,\d{3})*\.\d{2}/g) ?? []) found.add(m);
    }
  };
  lines.forEach(add);
  const port = lines[0]?.port_name as string | undefined;
  for (const cat of new Set(lines.map((l) => l.expense_category as string))) {
    if (!port) break;
    (await rows(analytics, historySql, { port, cat })).forEach(add);
    (await rows(analytics, competingSql, { port, cat })).forEach(add);
  }
  return found;
}

export default createAgent({
  ephemeral: true,
  // its own MLflow experiment (resources/quote_negotiator.experiment.yml): the whole system prompt is
  // `negotiator` in the agent's schema (alias production, changes without a deploy) and every turn is traced there
  model: agentModel('quote-negotiator'),
  baseSystemPrompt: fromRegistry('quote-negotiator'),
  instructions: '',
  tools(plugins) {
    const analytics = analyticsOf(plugins);
    return {
      get_quote: tool({
        description: 'The open PDA quote: port, vessel, agent and every quoted line with its benchmark (EUR).',
        schema: z.object({ proforma_id: z.number().int() }),
        annotations: { effect: 'read' },
        execute: ({ proforma_id }) => rows(analytics, quoteSql, { p: proforma_id }),
      }),
      get_price_history: tool({
        description: 'Final amounts (EUR) paid for this expense at this port on past approved calls, newest first.',
        schema: z.object({ port_name: z.string(), expense_category: z.string() }),
        annotations: { effect: 'read' },
        execute: ({ port_name, expense_category }) => rows(analytics, historySql, { port: port_name, cat: expense_category }),
      }),
      get_competing_quotes: tool({
        description: 'Past requests for quotes for this expense at this port: lowest, accepted and highest quote (EUR).',
        schema: z.object({ port_name: z.string(), expense_category: z.string() }),
        annotations: { effect: 'read' },
        execute: ({ port_name, expense_category }) => rows(analytics, competingSql, { port: port_name, cat: expense_category }),
      }),
      submit_draft: tool({
        description: 'Submit the finished email. Call once, at the end. Returns the amounts that were not found in the data.',
        schema: z.object({
          proforma_id: z.number().int(),
          subject: z.string(),
          body: z.string().describe('The email text, plain text with line breaks'),
          lines: z.array(z.object({
            expense_name: z.string(), quoted_eur: z.number(), target_eur: z.number(), evidence: z.string(),
          })),
        }),
        // read: the draft is only shown to the analyst; saving it is a separate, confirmed step in the app
        annotations: { effect: 'read' },
        execute: async ({ proforma_id, body }) => {
          const known = await knownAmounts(analytics, proforma_id);
          const amounts = body.match(/\d{1,3}(?:,\d{3})*\.\d{2}(?!\d)(?!\s*%)/g) ?? [];
          return { unverified_amounts: [...new Set(amounts.filter((a) => !known.has(a)))].sort() };
        },
      }),
    };
  },
});
