// A small, safe markdown subset for agent answers: paragraphs, bold, lists, pipe tables. Text is escaped first.
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c);
// bold only around text without asterisks, so masked accounts (NL** **** 5181) stay as they are
const inline = (s: string) => s.replace(/\*\*([^*\s][^*]*?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');

export function toHtml(text: string): string {
  const lines = esc(text || '').split('\n');
  let out = '';
  let open = false;
  let table: string[] = [];
  const flush = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r)).map((r) => r.replace(/^\s*\||\|\s*$/g, '').split('|').map((c) => inline(c.trim())));
    out += `<table><tr>${rows[0].map((c) => `<th>${c}</th>`).join('')}</tr>${rows.slice(1).map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
    table = [];
  };
  for (const l of lines) {
    if (/^\s*\|.*\|\s*$/.test(l)) { if (open) { out += '</ul>'; open = false; } table.push(l); continue; }
    flush();
    const li = l.match(/^(\s*)[-*]\s+(.*)/) || l.match(/^(\s*)\d+\.\s+(.*)/);
    if (li) { if (!open) { out += '<ul>'; open = true; } out += `<li${li[1].length >= 2 ? ' class="sub"' : ''}>${inline(li[2])}</li>`; continue; }
    if (open) { out += '</ul>'; open = false; }
    if (l.trim()) out += `<p>${inline(l.replace(/^#+\s*/, ''))}</p>`;
  }
  flush();
  if (open) out += '</ul>';
  return out;
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  // eslint-disable-next-line react/no-danger -- escaped above, only our own tags are added
  return <div className={className} dangerouslySetInnerHTML={{ __html: toHtml(text) }} />;
}
