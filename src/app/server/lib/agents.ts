// The code agents and their MLflow experiments, one per agent (resources/<agent>.experiment.yml). An agent's
// experiment points at the agent's own schema, which holds its prompt (the experiment's Prompts tab) and its traces
// (Delta tables, the Traces tab). The app gets the experiment ids and reads both locations from the experiment tags.
import * as mlflow from '@mlflow/core';
import { ucLocationFromExperimentTags } from '@mlflow/core/dist/core/destination.js';
import type { UnityCatalogLocation } from '@mlflow/core/dist/core/entities/trace_location.js';

/** Agent id (folder under server/agents) -> the env var with its experiment id (resources/app.yml). */
const EXPERIMENT_ENV = {
  'port-assistant': 'PORT_ASSISTANT_EXPERIMENT_ID',
  'quote-negotiator': 'QUOTE_NEGOTIATOR_EXPERIMENT_ID',
  'timeline-summarizer': 'TIMELINE_SUMMARIZER_EXPERIMENT_ID',
} as const;

export type AgentId = keyof typeof EXPERIMENT_ENV;
export const AGENT_IDS = Object.keys(EXPERIMENT_ENV) as AgentId[];

export type AgentExperiment = {
  experimentId: string;
  /** catalog.schema of the agent's prompt (tag mlflow.promptRegistryLocation) */
  promptSchema: string;
  /** where the agent's traces are written; null when the experiment has no UC trace location */
  traces: UnityCatalogLocation | null;
};

/** MLflow client as the app's service principal (or the CLI profile in local development). */
export function mlflowClient(): mlflow.MlflowClient {
  const profile = process.env.DATABRICKS_CONFIG_PROFILE?.trim();
  const trackingUri = profile ? `databricks://${profile}` : 'databricks';
  const host = process.env.DATABRICKS_HOST?.trim();
  const authProvider = mlflow.createAuthProvider({ trackingUri, ...(host ? { host: /^https?:\/\//.test(host) ? host : `https://${host}` } : {}) });
  return new mlflow.MlflowClient({ trackingUri, authProvider });
}

async function resolve(): Promise<Record<AgentId, AgentExperiment>> {
  const client = mlflowClient();
  const entries = await Promise.all(AGENT_IDS.map(async (agent) => {
    const experimentId = process.env[EXPERIMENT_ENV[agent]]?.trim();
    if (!experimentId) throw new Error(`${EXPERIMENT_ENV[agent]} is not set`);
    const experiment = await client.getExperiment(experimentId);
    const tags = experiment?.tags ?? {};
    const promptSchema = tags['mlflow.promptRegistryLocation'];
    if (!promptSchema) throw new Error(`experiment ${experimentId} of ${agent} has no mlflow.promptRegistryLocation tag`);
    return [agent, { experimentId, promptSchema, traces: ucLocationFromExperimentTags(tags) }] as const;
  }));
  return Object.fromEntries(entries) as Record<AgentId, AgentExperiment>;
}

let resolved: Promise<Record<AgentId, AgentExperiment>> | undefined;
/** The agents' experiments, read once at startup. */
export function agentExperiments(): Promise<Record<AgentId, AgentExperiment>> {
  resolved ??= resolve();
  return resolved;
}
