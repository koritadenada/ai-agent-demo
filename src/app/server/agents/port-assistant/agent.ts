// Port Assistant: questions in plain language. A custom agent that calls the three Genie agents (each owns one data
// area) and two document tools, as the signed-in user. Its prompt comes from the registry (port_assistant).
import { createAgent, tool } from '@databricks/appkit/beta';
import { z } from 'zod';
import { GOLD } from '../../lib/config';
import { askGenie, genieOf } from '../../lib/genie';
import { rows } from '../../lib/sql';
import { fromRegistry } from '../../lib/prompts';
import { agentModel } from '../../lib/tracing';
import { analyticsOf } from '../../lib/tools';

// tool name, genie space alias (server.ts), what that agent owns
const GENIE: [string, string, string][] = [
  ['ask_port_costs', 'port_costs', 'Port costs and benchmarks (cost per call, final vs quote, benchmarks, savings, competing and flagged quotes)'],
  ['ask_da_audit', 'da_audit', 'DA audit (final lines vs quote and invoice page, verdicts, analyst checks, bank checks, payments on hold, document quality)'],
  ['ask_da_operations', 'da_operations', 'DA operations (appointments, cancellations, workflow durations, statement of facts events)'],
];

export default createAgent({
  default: true,
  // its own MLflow experiment (resources/port_assistant.experiment.yml): the whole system prompt is
  // `port_assistant` in the agent's schema (alias production, changes without a deploy) and every turn is traced there
  model: agentModel('port-assistant'),
  baseSystemPrompt: fromRegistry('port-assistant'),
  instructions: '',
  tools(plugins) {
    const analytics = analyticsOf(plugins);
    const genie = genieOf(plugins);
    return {
      ...Object.fromEntries(GENIE.map(([name, alias, about]) => [name, tool({
        description: `Ask the ${about} Genie agent one precise question in plain language. Returns its answer, the SQL it ran and the rows.`,
        schema: z.object({ question: z.string() }),
        annotations: { effect: 'read' },
        execute: ({ question }) => askGenie(genie, alias, question),
      })])),
      search_documents: tool({
        description:
          'Keyword search over the text of every port call PDF (PDA quotes, final DA packs, statements of facts). Returns pages with port call, document type, page number and a snippet; account numbers are masked.',
        schema: z.object({
          query: z.string().describe('Words to look for, for example: pilotage invoice'),
          port_call: z.number().int().optional().describe('Only this port call id, when the question names one'),
        }),
        annotations: { effect: 'read' },
        execute: ({ query, port_call }) =>
          rows(analytics, `SELECT * FROM ${GOLD}.search_documents(:q, ${port_call ? 'CAST(:pc AS BIGINT)' : 'NULL'})`,
            port_call ? { q: query, pc: port_call } : { q: query }),
      }),
      port_call_timeline: tool({
        description: 'The ordered events of one port call from its statement of facts, with the page of each event.',
        schema: z.object({ port_call: z.number().int().describe('The port call id, for example 20217') }),
        annotations: { effect: 'read' },
        execute: ({ port_call }) => rows(analytics, `SELECT * FROM ${GOLD}.port_call_timeline(:pc)`, { pc: port_call }),
      }),
    };
  },
});
