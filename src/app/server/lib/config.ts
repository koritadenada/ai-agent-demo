// Where the data lives, from the bundle (resources/app.yml) or .env in development.
function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is not set`);
  return value;
}

export const GOLD = required('GOLD_SCHEMA');
export const SILVER = required('SILVER_SCHEMA');
export const APP = required('APP_SCHEMA');
export const PROMPT_ALIAS = process.env.PROMPT_ALIAS?.trim() || 'production';
export const SPACES = {
  port_costs: required('PORT_COSTS_SPACE_ID'),
  da_audit: required('DA_AUDIT_SPACE_ID'),
  da_operations: required('DA_OPERATIONS_SPACE_ID'),
};
