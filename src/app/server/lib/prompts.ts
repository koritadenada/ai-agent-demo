// Each code agent's system prompt comes from the MLflow Prompt Registry, in the agent's own schema (the one its
// experiment points at, alias `production`), read as the app's service principal and refreshed every few minutes,
// so a new version behind the alias changes the agent without a deploy. config/prompts.json holds the seeds
// (registered by the setup job) and is the fallback.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createWorkspaceClient } from '@databricks/appkit';
import { AGENT_IDS, agentExperiments, type AgentId } from './agents';
import { PROMPT_ALIAS } from './config';

type PromptSeed = { prompt: string; template: string; model: string | null };
const SEEDS = JSON.parse(readFileSync(join(process.cwd(), 'config', 'prompts.json'), 'utf8')) as Record<AgentId, PromptSeed>;

const loaded: Partial<Record<AgentId, { name: string; template: string; version: string }>> = {};

async function load(agent: AgentId): Promise<void> {
  try {
    const name = `${(await agentExperiments())[agent].promptSchema}.${SEEDS[agent].prompt}`;
    const response = await createWorkspaceClient().request({
      method: 'GET',
      path: `/api/2.0/mlflow/unity-catalog/prompts/${name}/versions/by-alias/${PROMPT_ALIAS}`,
    });
    const v = (await response.json()) as { template: string; version: string };
    const template = v.template.startsWith('"') ? (JSON.parse(v.template) as string) : v.template;
    loaded[agent] = { name, template, version: String(v.version) };
  } catch (err) {
    if (!loaded[agent]) console.warn(`[prompts] ${agent} from the repo seed: ${(err as Error).message.split('. Config:')[0]}`);
  }
}

export async function refreshPrompts(): Promise<void> {
  await Promise.all(AGENT_IDS.map(load));
}

export function startPromptRefresh(): void {
  void refreshPrompts();
  setInterval(() => void refreshPrompts(), 5 * 60_000).unref();
}

/** An agent's system prompt (its baseSystemPrompt): the registry version behind the alias, read at every turn. */
export function fromRegistry(agent: AgentId): () => string {
  if (!SEEDS[agent]) throw new Error(`no seed for ${agent} in config/prompts.json`);
  return () => loaded[agent]?.template ?? SEEDS[agent].template;
}

/** The prompt version an agent runs on, linked to each of its traces; undefined while on the repo seed. */
export function promptRef(agent: AgentId): { name: string; version: string } | undefined {
  const p = loaded[agent];
  return p && { name: p.name, version: p.version };
}

/** Prompt name -> the version in use, for /api/config. */
export function promptVersions(): Record<string, string> {
  return Object.fromEntries(AGENT_IDS.map((agent) => {
    const p = loaded[agent];
    return [SEEDS[agent].prompt, p ? `${p.name}@${PROMPT_ALIAS} v${p.version}` : `${SEEDS[agent].prompt}@repo-seed`];
  }));
}
