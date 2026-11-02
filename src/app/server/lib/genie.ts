// The Genie agents as Port Assistant tools. The genie plugin asks as the signed-in user; its answers can carry
// BigInt values (row counts), which a tool result cannot serialize, so they are turned into numbers here, and the
// status updates Genie streams along the way are left out.
type GenieLike = { sendMessage: (alias: string, content: string) => AsyncIterable<unknown> };

export function genieOf(plugins: Record<string, unknown>): GenieLike {
  const g = plugins.genie;
  if (g && typeof g === 'object' && 'sendMessage' in g && typeof g.sendMessage === 'function') {
    const send = g.sendMessage.bind(g) as GenieLike['sendMessage'];
    return { sendMessage: send };
  }
  throw new Error('The genie plugin is not registered');
}

const plain = (value: unknown): unknown =>
  JSON.parse(JSON.stringify(value, (_k, v: unknown) => (typeof v === 'bigint' ? Number(v) : v)));

export async function askGenie(genie: GenieLike, alias: string, question: string): Promise<unknown> {
  const events: unknown[] = [];
  for await (const event of genie.sendMessage(alias, question)) {
    if (!(event && typeof event === 'object' && 'type' in event && event.type === 'status')) events.push(event);
  }
  return plain(events);
}
