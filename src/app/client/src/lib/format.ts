export const num = (n: number | string | null | undefined, d = 2) =>
  n == null || n === '' ? '' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
export const month = (s?: string | null) =>
  s ? new Date(s).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '';
export const when = (s?: string | null) =>
  s ? new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const VERDICT: Record<string, string> = {
  MATCH: 'Matches the quote', OVER_QUOTE: 'Above the quote', UNDER_QUOTE: 'Below the quote',
  INVOICE_MISMATCH: 'Invoice page differs', CURRENCY_MISMATCH: 'Currency differs', NO_EVIDENCE: 'No invoice page',
};
export const ACTION: Record<string, string> = { accept: 'ok', review: 'review', dispute: 'dispute' };
export const DECISION: Record<string, [string, string]> = {
  accept: ['ok', 'Accepted'], dispute: ['dispute', 'Disputed'], hold: ['hold', 'On hold'],
};
export const DOC: Record<string, string> = {
  final_da_pack: 'Final DA pack', pda_quote: 'PDA quote', statement_of_facts: 'Statement of facts', other: 'Other document',
};
export const SECTION: Record<string, string> = { PORT_EXPENSES: 'Port expenses', HUSBANDRY: 'Husbandry' };

/** Arrays come back as JSON text from the warehouse. */
export function list<T>(v: unknown): T[] {
  if (Array.isArray(v)) return v as T[];
  if (typeof v === 'string' && v.startsWith('[')) {
    try { return JSON.parse(v) as T[]; } catch { return []; }
  }
  return [];
}
