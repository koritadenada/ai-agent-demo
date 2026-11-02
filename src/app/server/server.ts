// Port call agents app (AppKit). Plugins:
//   agents     Port Assistant, Quote Negotiator, Timeline Summarizer (server/agents), as the signed-in user,
//              traced to MLflow, conversations kept in Lakebase
//   analytics  the screens' queries (config/queries/*.obo.sql, as the user) and the confirmed writes below
//   files      the PDFs of the documents volume, read as the user
//   genie      the three Genie agents, used by the Port Assistant
//   lakebase   the chat history
import { analytics, createApp, files, genie, lakebase, server, sql } from '@databricks/appkit';
import { agents } from '@databricks/appkit/beta';
import { propagation } from '@opentelemetry/api';
import type { Request } from 'express';
import { z } from 'zod';
import { APP, GOLD, SILVER, SPACES } from './lib/config';
import { promptFor, promptVersions, startPromptRefresh } from './lib/prompts';
import { LakebaseThreadStore } from './lib/threads';

const threads = new LakebaseThreadStore();

const Decision = z.object({ decision: z.enum(['accept', 'dispute', 'hold']), note: z.string().max(2000).default('') });
const Draft = z.object({
  subject: z.string().min(1).max(300),
  body: z.string().min(1).max(10000),
  lines: z.array(z.unknown()).default([]),
  unverified_amounts: z.array(z.string()).default([]),
});

const userOf = (req: Request) => String(req.headers['x-forwarded-email'] ?? req.headers['x-forwarded-user'] ?? 'local developer');

createApp({
  // no query cache: a decision or a saved draft shows on the next read, and gold changes with every refresh
  cache: { enabled: false },
  plugins: [
    agents({ auth: 'on-behalf-of-user', threadStore: threads, baseSystemPrompt: (ctx) => promptFor(ctx.agentName) }),
    analytics(),
    files({ volumes: { files: { auth: 'on-behalf-of-user' } } }),  // the documents volume
    genie({ spaces: SPACES }),
    lakebase(),
    server(),
  ],
  async onPluginsReady(appkit) {
    // MLflow starts a trace only at a span without a parent. The Apps proxy sends a traceparent header, and
    // continuing it would give every agent turn a remote parent and no trace, so incoming trace context is ignored.
    propagation.disable();
    await threads.attach((text, params) => appkit.lakebase.query(text, params));
    startPromptRefresh();

    appkit.server.extend((app) => {
      app.get('/api/config', (req, res) => {
        res.json({ gold: GOLD, silver: SILVER, app: APP, user: userOf(req), prompts: promptVersions() });
      });

      // Accept, dispute or hold a final DA. The analyst confirms in the UI first; written as the analyst.
      app.post('/api/fdas/:id/decision', async (req, res) => {
        const parsed = Decision.safeParse(req.body);
        const id = Number(req.params.id);
        if (!parsed.success || !Number.isInteger(id)) {
          res.status(422).json({ error: 'decision must be accept, dispute or hold' });
          return;
        }
        try {
          const db = appkit.analytics.asUser(req);
          await db.query(
            `INSERT INTO ${APP}.analyst_decisions
             SELECT uuid(), b.evaluation_id, b.port_call_id, :decision, :note, CAST(b.lines_flagged AS INT), :user, current_timestamp()
             FROM ${GOLD}.port_bill_analysis b WHERE b.evaluation_id = :id`,
            { id: sql.bigint(id), decision: sql.string(parsed.data.decision), note: sql.string(parsed.data.note), user: sql.string(userOf(req)) },
          );
          res.json({ saved: true });
        } catch (err) {
          res.status(500).json({ error: (err as Error).message });
        }
      });

      // Save a negotiation draft the analyst reviewed. Nothing is sent to the port agent.
      app.post('/api/quotes/:id/drafts', async (req, res) => {
        const parsed = Draft.safeParse(req.body);
        const id = Number(req.params.id);
        if (!parsed.success || !Number.isInteger(id)) {
          res.status(422).json({ error: 'subject and body are required' });
          return;
        }
        try {
          const d = parsed.data;
          await appkit.analytics.asUser(req).query(
            `INSERT INTO ${APP}.negotiation_drafts
             SELECT uuid(), c.proforma_id, c.port_call_id, c.agent_name, :subject, :body, :lines, :unverified,
                    :prompt, :model, :user, current_timestamp()
             FROM ${GOLD}.port_call_costs c WHERE c.proforma_id = :id`,
            {
              id: sql.bigint(id), subject: sql.string(d.subject), body: sql.string(d.body),
              lines: sql.string(JSON.stringify(d.lines)), unverified: sql.string(JSON.stringify(d.unverified_amounts)),
              prompt: sql.string(promptVersions().negotiator ?? ''),
              model: sql.string(process.env.DATABRICKS_SERVING_ENDPOINT_NAME ?? ''), user: sql.string(userOf(req)),
            },
          );
          res.json({ saved: true });
        } catch (err) {
          res.status(500).json({ error: (err as Error).message });
        }
      });
    });
  },
}).catch(console.error);
