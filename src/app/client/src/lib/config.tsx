// Schema names and the signed-in user, from the server once; every query takes the schemas as parameters.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { sql } from '@databricks/appkit-ui/js';

export type AppConfig = { gold: string; silver: string; app: string; user: string; prompts: Record<string, string> };
const Ctx = createContext<AppConfig | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch('/api/config').then((r) => r.json() as Promise<AppConfig>).then(setConfig).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <main><div className="card">Could not load the app configuration: {error}</div></main>;
  if (!config) return <main><div className="loading"><div className="spin" />Loading</div></main>;
  return <Ctx.Provider value={config}>{children}</Ctx.Provider>;
}

export function useConfig(): AppConfig {
  const c = useContext(Ctx);
  if (!c) throw new Error('useConfig outside ConfigProvider');
  return c;
}

/** The schema parameters every query takes. */
export function useSchemas() {
  const c = useConfig();
  return { gold: sql.string(c.gold), silver: sql.string(c.silver), app: sql.string(c.app) };
}
