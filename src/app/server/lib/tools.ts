// The analytics plugin as the agent tools see it: a query function that runs with the caller's identity.
import type { Analytics } from './sql';

export function analyticsOf(plugins: Record<string, unknown>): Analytics {
  const a = plugins.analytics;
  if (a && typeof a === 'object' && 'query' in a && typeof a.query === 'function') {
    const query = a.query.bind(a) as Analytics['query'];
    return { query };
  }
  throw new Error('The analytics plugin is not registered');
}
