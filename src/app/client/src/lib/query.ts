// useAnalyticsQuery with typed values: the warehouse returns booleans and numbers as text ("false", "0"), which
// would read as true in the UI. Rows are converted to the types the generated query types already promise.
import { useMemo } from 'react';
import { useAnalyticsQuery } from '@databricks/appkit-ui/react';

const NUMBER = /^-?\d+(\.\d+)?(E-?\d+)?$/i;

function typed(row: unknown): unknown {
  if (!row || typeof row !== 'object') return row;
  return Object.fromEntries(Object.entries(row).map(([k, v]) => [k,
    v === 'true' ? true : v === 'false' ? false : typeof v === 'string' && NUMBER.test(v) ? Number(v) : v]));
}

export function useQuery<K extends Parameters<typeof useAnalyticsQuery>[0]>(
  key: K,
  params?: Parameters<typeof useAnalyticsQuery<unknown, K>>[1],
  options?: Parameters<typeof useAnalyticsQuery<unknown, K>>[2],
): ReturnType<typeof useAnalyticsQuery<unknown, K>> {
  const result = useAnalyticsQuery<unknown, K>(key, params, options);
  const data = useMemo(() => (Array.isArray(result.data) ? result.data.map(typed) : result.data), [result.data]);
  return { ...result, data: data as typeof result.data };
}
