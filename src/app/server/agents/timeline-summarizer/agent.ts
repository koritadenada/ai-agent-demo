// Timeline Summarizer: writes the account of one port call from the events read from its statement of facts.
// One-shot (ephemeral): nothing is kept in the chat history. Prompt from the registry (port_call_story).
import { createAgent, tool } from '@databricks/appkit/beta';
import { z } from 'zod';
import { GOLD, SILVER } from '../../lib/config';
import { rows } from '../../lib/sql';
import { analyticsOf } from '../../lib/tools';

export default createAgent({
  ephemeral: true,
  instructions: 'Write the account of the port call from the tool result only.',
  tools(plugins) {
    const analytics = analyticsOf(plugins);
    return {
      get_port_call: tool({
        description: 'The port call (vessel, port, agent, DA milestones) and its statement of facts events with pages.',
        schema: z.object({ port_call: z.number().int() }),
        annotations: { effect: 'read' },
        execute: async ({ port_call }) => ({
          port_call: (await rows(analytics,
            `SELECT port_call_id, vessel_name, vessel_type, gross_tonnage, port_name, agent_name,
                    CAST(appointment_created_at AS STRING) AS appointment_created_at, CAST(pda_submitted_at AS STRING) AS pda_submitted_at,
                    CAST(fda_created_at AS STRING) AS fda_created_at, CAST(fda_approved_at AS STRING) AS fda_approved_at,
                    ROUND(fda_approval_hours, 1) AS fda_approval_hours
             FROM ${GOLD}.port_call_costs WHERE port_call_id = :pc`, { pc: port_call }))[0] ?? null,
          events: await rows(analytics,
            `SELECT e.event_order, e.event, CAST(e.event_time AS STRING) AS event_time, e.event_time_text, e.page_number
             FROM ${SILVER}.port_call_events e JOIN ${GOLD}.port_call_costs c ON c.proforma_id = e.proforma_id
             WHERE c.port_call_id = :pc ORDER BY e.event_order`, { pc: port_call }),
        }),
      }),
    };
  },
});
