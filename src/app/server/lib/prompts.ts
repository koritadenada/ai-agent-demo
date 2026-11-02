// Agent prompts come from the MLflow Prompt Registry (app schema, alias `production`), read as the app's service
// principal and refreshed every few minutes, so a new version behind the alias changes an agent without a deploy.
// config/prompts.json holds the seeds (registered by the setup job) and is the fallback.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createWorkspaceClient } from '@databricks/appkit';
import { APP, PROMPT_ALIAS } from './config';

type PromptSeed = { template: string; model: string | null };
const SEEDS = JSON.parse(readFileSync(join(process.cwd(), 'config', 'prompts.json'), 'utf8')) as Record<string, PromptSeed>;

/** Agent id (folder under server/agents) -> prompt name in the registry. */
export const AGENT_PROMPTS: Record<string, string> = {
  'port-assistant': 'port_assistant',
  'quote-negotiator': 'negotiator',
  'timeline-summarizer': 'port_call_story',
};

const loaded: Record<string, { template: string; version: string }> = {};

async function load(name: string): Promise<void> {
  try {
    const client = createWorkspaceClient();
    const response = await client.request({
      method: 'GET',
      path: `/api/2.0/mlflow/unity-catalog/prompts/${APP}.${name}/versions/by-alias/${PROMPT_ALIAS}`,
    });
    const v = (await response.json()) as { template: string; version: string };
    const template = v.template.startsWith('"') ? (JSON.parse(v.template) as string) : v.template;
    loaded[name] = { template, version: `${name}@${PROMPT_ALIAS} v${v.version}` };
  } catch (err) {
    if (!loaded[name]) console.warn(`[prompts] ${name} from the repo seed: ${(err as Error).message.split('. Config:')[0]}`);
  }
}

export async function refreshPrompts(): Promise<void> {
  await Promise.all(Object.keys(SEEDS).filter((n) => !n.startsWith('_')).map(load));
}

export function startPromptRefresh(): void {
  void refreshPrompts();
  setInterval(() => void refreshPrompts(), 5 * 60_000).unref();
}

export function promptFor(agentName: string): string {
  const name = AGENT_PROMPTS[agentName];
  return (name && (loaded[name]?.template ?? SEEDS[name]?.template)) || '';
}

export function promptVersions(): Record<string, string> {
  return Object.fromEntries(
    Object.values(AGENT_PROMPTS).map((n) => [n, loaded[n]?.version ?? `${n}@repo-seed`]),
  );
}
