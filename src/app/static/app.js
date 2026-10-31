// Port call agents: one page, hash routes, no build step.
const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');

// ---------- icons (inline SVG, stroke) ----------
const svg = (d, w = 24) => `<svg viewBox="0 0 ${w} ${w}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const I = {
  mark: `<svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="15" fill="#000D4C"/><path d="M7 19c2.2 0 2.2-1.6 4.5-1.6S13.8 19 16 19s2.2-1.6 4.5-1.6S22.8 19 25 19" stroke="#2AA8F2" stroke-width="2" stroke-linecap="round"/><path d="M7 23c2.2 0 2.2-1.6 4.5-1.6S13.8 23 16 23s2.2-1.6 4.5-1.6S22.8 23 25 23" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".55"/><circle cx="16" cy="11" r="3.2" fill="#3C45E6" stroke="#fff" stroke-width="1.6"/></svg>`,
  home: svg('<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>'),
  review: svg('<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/><path d="M9 14l2 2 4-4"/>'),
  deal: svg('<path d="M4 6h16v10H8l-4 4z"/><path d="M8 10h8M8 13h5"/>'),
  ship: svg('<path d="M3 17l2 4h14l2-4z"/><path d="M5 17V9h14v8"/><path d="M9 9V5h6v4"/><path d="M12 5V3"/>'),
  hal: svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/>'),
  page: svg('<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>'),
  check: svg('<path d="M5 12l4 4 10-10"/>'),
  alert: svg('<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5v.01"/>'),
  send: svg('<path d="M4 12l16-8-6 16-3-7z"/>'),
  copy: svg('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>'),
  save: svg('<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h8V3M8 21v-7h8v7"/>'),
  back: svg('<path d="M15 6l-6 6 6 6"/>'),
  bank: svg('<path d="M3 10l9-6 9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18"/>'),
  spark: svg('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>'),
  clock: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  euro: svg('<path d="M17 6a7 7 0 1 0 0 12"/><path d="M4 10h9M4 14h9"/>'),
};

// ---------- helpers ----------
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (n, d = 2) => n == null ? '' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const money = (n, c = 'EUR', d = 2) => n == null ? '<span class="muted">-</span>' : `${num(n, d)} <span class="muted small">${esc(c)}</span>`;
const date = s => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '';
const when = s => s ? new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const month = s => s ? new Date(s).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '';
const loading = (t = 'Loading') => `<div class="loading"><div class="spin"></div>${esc(t)}</div>`;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
}
function toast(t, err = false) {
  const el = document.createElement('div'); el.className = 'toast' + (err ? ' err' : ''); el.textContent = t;
  document.body.appendChild(el); setTimeout(() => el.remove(), 3500);
}
function confirmBox({ title, text, ok = 'Confirm', cls = '', note = false }) {
  return new Promise(resolve => {
    const m = document.createElement('div'); m.className = 'modal';
    m.innerHTML = `<div class="box"><h3>${esc(title)}</h3><p>${text}</p>
      ${note ? '<div class="field"><label>Note for the agent and the team (optional)</label><textarea id="note" rows="3"></textarea></div>' : ''}
      <div class="actions" style="justify-content:flex-end"><button class="btn ghost" data-a="0">Cancel</button><button class="btn ${cls}" data-a="1">${esc(ok)}</button></div></div>`;
    m.addEventListener('click', e => {
      const a = e.target.closest('[data-a]'); if (!a && e.target !== m) return;
      const yes = a && a.dataset.a === '1'; const n = $('#note', m)?.value || '';
      m.remove(); resolve(yes ? { note: n } : null);
    });
    document.body.appendChild(m); $('textarea, .btn:last-child', m)?.focus();
  });
}
// a small, safe markdown subset for agent answers: paragraphs, bold, lists, pipe tables
function md(t) {
  const lines = esc(t || '').split('\n'); let out = '', list = false, table = [];
  // bold only around text without asterisks, so masked accounts (NL** **** 5181) stay as they are
  const inline = s => s.replace(/\*\*([^*\s][^*]*?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter(r => !/^\s*\|?\s*:?-{2,}/.test(r)).map(r => r.replace(/^\s*\||\|\s*$/g, '').split('|').map(c => inline(c.trim())));
    out += `<table><tr>${rows[0].map(c => `<th>${c}</th>`).join('')}</tr>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
    table = [];
  };
  for (const l of lines) {
    if (/^\s*\|.*\|\s*$/.test(l)) { if (list) { out += '</ul>'; list = false; } table.push(l); continue; }
    flushTable();
    const li = l.match(/^(\s*)[-*]\s+(.*)/) || l.match(/^(\s*)\d+\.\s+(.*)/);
    if (li) { if (!list) { out += '<ul>'; list = true; } out += `<li${li[1].length >= 2 ? ' class="sub"' : ''}>${inline(li[2])}</li>`; continue; }
    if (list) { out += '</ul>'; list = false; }
    if (l.trim()) out += `<p>${inline(l.replace(/^#+\s*/, ''))}</p>`;
  }
  flushTable(); if (list) out += '</ul>';
  return out;
}

const VERDICT = { MATCH: 'Matches the quote', OVER_QUOTE: 'Above the quote', UNDER_QUOTE: 'Below the quote',
  INVOICE_MISMATCH: 'Invoice page differs', CURRENCY_MISMATCH: 'Currency differs', NO_EVIDENCE: 'No invoice page' };
const ACTION = { accept: ['ok', 'Accept'], review: ['review', 'Review'], dispute: ['dispute', 'Dispute'] };
const DECISION = { accept: ['ok', 'Accepted'], dispute: ['dispute', 'Disputed'], hold: ['hold', 'On hold'] };
const DOC = { final_da_pack: 'Final DA pack', pda_quote: 'PDA quote', statement_of_facts: 'Statement of facts', other: 'Other document' };
const SECTION = { PORT_EXPENSES: 'Port expenses', HUSBANDRY: 'Husbandry' };
const svc = (name, icon) => `<span class="svc">${I[icon]}${esc(name)}</span>`;
const decisionPill = d => d ? `<span class="pill ${DECISION[d][0]}">${DECISION[d][1]}</span>` : '<span class="pill info">To review</span>';

// ---------- shell ----------
const NAV = [['#/', 'Overview'], ['#/review', 'DA review'], ['#/negotiator', 'AI Negotiator'], ['#/port-calls', 'Port calls'], ['#/hal', 'HAL-9000']];
$('#brand').innerHTML = `${I.mark}<div><b>PortCall</b><span>Agents</span></div>`;
$('#askbtn').innerHTML = `${I.hal}Ask HAL-9000`;
api('/api/me').then(m => { $('#who').textContent = m.user; }).catch(() => {});

function setNav(hash) {
  $('#nav').innerHTML = NAV.map(([h, t]) => {
    const on = h === '#/' ? hash === '#/' || hash === '' : hash.startsWith(h);
    return `<a href="${h}" class="${on ? 'on' : ''}">${t}</a>`;
  }).join('');
}

const routes = [
  [/^#?\/?$/, overview],
  [/^#\/review$/, reviewList],
  [/^#\/review\/(\d+)$/, reviewDetail],
  [/^#\/negotiator$/, quoteList],
  [/^#\/negotiator\/(\d+)$/, quoteDetail],
  [/^#\/port-calls$/, portCallList],
  [/^#\/port-calls\/(\d+)$/, portCall],
  [/^#\/hal$/, hal],
];
async function route() {
  const h = location.hash || '#/'; setNav(h); window.scrollTo(0, 0);
  for (const [re, fn] of routes) {
    const m = h.match(re);
    if (m) { view.innerHTML = loading(); try { await fn(...m.slice(1)); } catch (e) { view.innerHTML = `<div class="card"><h3>${I.alert}Something went wrong</h3><p class="muted">${esc(e.message)}</p></div>`; } return; }
  }
  location.hash = '#/';
}
addEventListener('hashchange', route);

// ---------- overview ----------
async function overview() {
  const d = await api('/api/overview'); const k = d.kpi;
  view.innerHTML = `
    <section class="hero">
      <div class="eyebrow">Port call AI agents</div>
      <h1>Check <em>every</em> DA<br>against its documents.</h1>
      <div class="tagline">Quotes benchmarked, invoices read, bank details validated, before money moves.</div>
    </section>
    <div class="kpis">
      <div class="kpi accent"><div class="v">${k.fdas_to_review}<small>of ${k.fdas_checked}</small></div><div class="l">Final DAs waiting for a decision</div></div>
      <div class="kpi alert"><div class="v">${k.payments_on_hold}</div><div class="l">Payments on hold: bank details differ</div></div>
      <div class="kpi"><div class="v">${num(k.over_invoiced_eur, 0)}<small>EUR</small></div><div class="l">Invoiced above the quote on checked DAs</div></div>
      <div class="kpi good"><div class="v">${num(k.open_quote_savings_eur, 0)}<small>EUR</small></div><div class="l">To negotiate on ${k.open_quotes_flagged} open quotes</div></div>
    </div>
    <div class="grid g2">
      <div class="card"><div class="row-gap" style="justify-content:space-between"><h3>${I.review}Final DAs to decide</h3>${svc('SOF Port Bill Analysis', 'review')}</div>
        <div class="sub">Every line checked against its quote and its invoice page; bank details checked before payment.</div>
        <div class="list">${d.fdas.map(f => `
          <div class="item" onclick="location.hash='#/review/${f.evaluation_id}'">
            <div class="ico ${f.hold_payment ? 'red' : ''}">${f.hold_payment ? I.bank : I.review}</div>
            <div><div class="t">${esc(f.vessel_name)} at ${esc(f.port_name)}</div><div class="s">${esc(f.agent_name)} · port call ${f.port_call_id}</div></div>
            <div class="r"><div>${f.hold_payment ? '<span class="pill hold">Payment on hold</span>' : f.lines_flagged ? `<span class="pill review">${f.lines_flagged} lines to check</span>` : '<span class="pill ok">All lines match</span>'}</div>
              <div class="s" style="margin-top:4px">${decisionPill(f.decision)}</div></div>
          </div>`).join('')}</div>
        <div style="margin-top:12px"><a href="#/review" class="btn ghost sm">All final DAs</a></div>
      </div>
      <div class="card"><div class="row-gap" style="justify-content:space-between"><h3>${I.deal}Open quotes to negotiate</h3>${svc('AI Negotiator', 'deal')}</div>
        <div class="sub">PDA quotes above what this port usually costs for this vessel size, before the vessel arrives.</div>
        <div class="list">${d.quotes.filter(q => q.flagged_lines).map(q => `
          <div class="item" onclick="location.hash='#/negotiator/${q.proforma_id}'">
            <div class="ico green">${I.euro}</div>
            <div><div class="t">${esc(q.vessel_name)} at ${esc(q.port_name)}</div><div class="s">${esc(q.agent_name)} · ${q.flagged_lines} of ${q.lines} lines above the benchmark</div></div>
            <div class="r"><div class="t amt-ok">${q.saving_eur ? num(q.saving_eur) + ' EUR' : '-'}</div><div class="s">potential saving</div></div>
          </div>`).join('')}</div>
        <div style="margin-top:12px"><a href="#/negotiator" class="btn ghost sm">All open quotes</a></div>
      </div>
    </div>
    <div class="card" style="margin-top:20px">
      <div class="row-gap" style="justify-content:space-between"><h3>${I.hal}Ask HAL-9000</h3>${svc('HAL-9000', 'hal')}</div>
      <div class="sub">Costs, audits, operations and documents, in plain language, with your own data permissions.</div>
      <form class="composer" onsubmit="event.preventDefault(); sessionStorage.q = this.q.value; location.hash = '#/hal'">
        <input name="q" placeholder="For example: which ports were most expensive per call last month?" autocomplete="off">
        <button class="btn">${I.send}Ask</button>
      </form>
      <div class="small muted" style="margin-top:12px">Agreement of the automated checks with the DA analysts: <b>${num(k.agreement_pct, 1)}%</b> of verified lines.</div>
    </div>`;
}

// ---------- DA review ----------
let reviewFilter = 'todo';
async function reviewList() {
  const rows = await api('/api/fdas');
  const groups = { todo: r => !r.decision, hold: r => r.hold_payment, decided: r => !!r.decision, all: () => true };
  const draw = () => {
    const shown = rows.filter(groups[reviewFilter]);
    view.innerHTML = `
      <div class="pagehead"><div>${svc('SOF Port Bill Analysis', 'review')} ${svc('PDA/FDA Validator', 'bank')}
        <h2>Final DA review</h2><p>Each final DA, line by line against the quote and the supplier invoice pages, and the bank details against the platform.</p></div>
        <div class="tabs">${[['todo', 'To review'], ['hold', 'Payment on hold'], ['decided', 'Decided'], ['all', 'All']].map(([k, t]) =>
          `<button class="${reviewFilter === k ? 'on' : ''}" data-f="${k}">${t}<b>${rows.filter(groups[k]).length}</b></button>`).join('')}</div></div>
      <div class="tbl"><table>
        <tr><th>Vessel and port</th><th>Agent</th><th>Call</th><th class="num">Final DA</th><th>Lines</th><th>Payment</th><th>Decision</th></tr>
        ${shown.map(r => `<tr class="row" onclick="location.hash='#/review/${r.evaluation_id}'">
          <td><b>${esc(r.vessel_name)}</b><div class="exp">${esc(r.port_name)} · port call ${r.port_call_id}</div></td>
          <td>${esc(r.agent_name)}<div class="exp">${esc(r.buyer_name)}</div></td>
          <td class="nowrap">${month(r.call_month)}</td>
          <td class="num nowrap">${money(r.final_amount, r.currency)}</td>
          <td>${r.lines_flagged ? `<span class="pill review">${r.lines_flagged} of ${r.lines_checked} to check</span>` : `<span class="pill ok">${r.lines_checked} match</span>`}</td>
          <td>${r.hold_payment ? '<span class="pill hold">On hold</span>' : '<span class="pill ok">Details match</span>'}</td>
          <td>${decisionPill(r.decision)}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">Nothing here.</td></tr>'}
      </table></div>`;
    view.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { reviewFilter = b.dataset.f; draw(); });
  };
  draw();
}

async function reviewDetail(id) {
  const d = await api(`/api/fdas/${id}`); const f = d.fda, p = d.payment;
  const pack = d.documents.find(x => x.doc_type === 'final_da_pack');
  const bySection = {};
  d.lines.forEach(l => (bySection[l.expense_section || 'OTHER'] ||= []).push(l));
  const sum = (ls, k) => ls.reduce((a, l) => a + (l[k] || 0), 0);
  const rowsHtml = Object.entries(bySection).map(([sec, ls], i) => `
    <tr class="sec"><td colspan="5">${String.fromCharCode(65 + i)}. ${esc(SECTION[sec] || sec)}</td></tr>
    ${ls.map(l => {
      const [cls] = ACTION[l.review_action] || ['muted'];
      return `<tr>
        <td><b>${esc(l.line_name)}</b><div class="exp">${esc(l.explanation)}</div></td>
        <td class="num nowrap">${num(l.quoted_amount)}</td>
        <td class="num nowrap amt-${cls === 'ok' ? 'ok' : cls}">${num(l.final_amount)}</td>
        <td class="nowrap">${(l.evidence_pages || []).map(pg => `<span class="pagechip" data-file="${l.file_item_id}" data-page="${pg}">${I.page}p. ${pg}</span>`).join(' ') || '<span class="muted small">none</span>'}
          ${l.invoiced_amount != null && l.invoiced_currency !== f.currency ? `<div class="exp">${num(l.invoiced_amount)} ${esc(l.invoiced_currency)}</div>` : ''}</td>
        <td><span class="pill ${cls}">${esc(VERDICT[l.verdict] || l.verdict)}</span>${l.variance_vs_quote_pct != null && Math.abs(l.variance_vs_quote_pct) >= .05 ? `<div class="exp">${l.variance_vs_quote_pct > 0 ? '+' : ''}${num(l.variance_vs_quote_pct, 1)}% vs quote</div>` : ''}</td></tr>`;
    }).join('')}
    <tr class="subtotal"><td>Subtotal</td><td class="num">${num(sum(ls, 'quoted_amount'))}</td><td class="num">${num(sum(ls, 'final_amount'))}</td><td colspan="2"></td></tr>`).join('');
  const bankCard = p ? `<div class="card"><div class="row-gap" style="justify-content:space-between"><h3>${I.bank}Bank details before payment</h3>${svc('PDA/FDA Validator', 'bank')}</div>
          <div class="sub">What the DA pack says against what the platform has on file. Low-confidence readings never count as a match.</div>
          ${(p.field_checks || []).map(c => `<div class="check"><span class="pill ${c.status === 'MATCH' ? 'ok' : 'dispute'}">${c.status === 'MATCH' ? 'Match' : 'Differs'}</span>
            <div><div class="n">${esc(c.name)}</div><div class="e">${esc(c.explanation)}${c.confidence != null ? ` · read with ${num(c.confidence * 100, 0)}% confidence` : ''}</div></div></div>`).join('')}
        </div>` : '';
  view.innerHTML = `
    <a class="back" href="#/review">${I.back}All final DAs</a>
    <div class="pagehead"><div><h2>${esc(f.vessel_name)} at ${esc(f.port_name)}</h2>
      <p>${esc(f.agent_name)} for ${esc(f.buyer_name)} · port call <a href="#/port-calls/${f.port_call_id}">${f.port_call_id}</a> · ${month(f.call_month)}</p></div>
      <div class="row-gap">${decisionPill(f.decision)}${p?.hold_payment ? '<span class="pill hold">Payment on hold</span>' : ''}</div></div>
    <div class="grid g-main">
      <div class="grid">
        ${p?.hold_payment ? bankCard : ''}
        <div class="card flush"><div class="head row-gap" style="justify-content:space-between"><div><h3>${I.review}Quote against final bill</h3>
          <div class="sub" style="margin:0">${f.lines_flagged ? `${f.lines_flagged} of ${f.lines_checked} lines need a look` : `All ${f.lines_checked} lines match`}. Click a page to see the invoice.</div></div>${svc('SOF Port Bill Analysis', 'review')}</div>
          <div class="tbl" style="border-radius:0;border-left:0;border-right:0;border-bottom:0"><table>
            <tr><th>Expense</th><th class="num">Quoted (${esc(f.currency)})</th><th class="num">Final (${esc(f.currency)})</th><th>Invoice page</th><th>Check</th></tr>
            ${rowsHtml}
            <tr class="total"><td>Total</td><td class="num">${num(sum(d.lines, 'quoted_amount'))}</td><td class="num">${num(sum(d.lines, 'final_amount'))}</td><td colspan="2"></td></tr>
          </table></div></div>
        ${p?.hold_payment ? '' : bankCard}
        <div class="card"><h3>${I.check}Decision</h3>
          <div class="sub">Saved to the DA history after you confirm. ${d.decisions.length ? '' : 'No decision yet.'}</div>
          <div class="actions">
            <button class="btn green" data-d="accept">${I.check}Accept</button>
            <button class="btn orange" data-d="dispute">${I.deal}Dispute</button>
            <button class="btn red" data-d="hold">${I.alert}Hold payment</button></div>
          ${d.decisions.map(x => `<div class="check"><span class="pill ${DECISION[x.decision][0]}">${DECISION[x.decision][1]}</span><div><div class="n" style="text-transform:none">${esc(x.decided_by)} · ${when(x.decided_at)}</div>${x.note ? `<div class="e">${esc(x.note)}</div>` : ''}</div></div>`).join('')}
        </div>
      </div>
      <div class="card viewer"><div class="row-gap" style="justify-content:space-between;margin-bottom:12px"><h3>${I.page}Documents</h3>
        <div class="row-gap">${d.documents.map(x => `<span class="pagechip" data-file="${x.file_item_id}" data-page="1">${esc(DOC[x.doc_type] || x.doc_type)}</span>`).join('')}</div></div>
        <div id="pdf">${pack ? '' : '<div class="empty">No final DA pack received</div>'}</div></div>
    </div>`;
  const open = (file, page) => {
    $('#pdf').innerHTML = `<iframe title="Document" src="/api/documents/${file}?p=${page}#page=${page}&view=FitH"></iframe>`;
    view.querySelectorAll('.pagechip').forEach(c => c.classList.toggle('on', c.dataset.file === String(file) && c.dataset.page === String(page)));
  };
  view.querySelectorAll('.pagechip').forEach(c => c.onclick = () => open(c.dataset.file, c.dataset.page));
  if (pack) open(pack.file_item_id, 1);
  view.querySelectorAll('[data-d]').forEach(b => b.onclick = async () => {
    const k = b.dataset.d;
    const text = { accept: `Accept the final DA of ${esc(f.vessel_name)} at ${esc(f.port_name)} for payment?`,
      dispute: `Dispute this final DA with ${esc(f.agent_name)}? ${f.lines_flagged} lines were flagged.`,
      hold: 'Hold the payment of this final DA until the bank details are confirmed?' }[k];
    const ok = await confirmBox({ title: { accept: 'Accept final DA', dispute: 'Dispute final DA', hold: 'Hold payment' }[k], text,
      ok: { accept: 'Accept', dispute: 'Dispute', hold: 'Hold payment' }[k], cls: { accept: 'green', dispute: 'orange', hold: 'red' }[k], note: true });
    if (!ok) return;
    try { await api(`/api/fdas/${id}/decision`, { method: 'POST', body: { decision: k, note: ok.note } }); toast('Decision saved'); reviewDetail(id); }
    catch (e) { toast(e.message, true); }
  });
}

// ---------- AI Negotiator ----------
async function quoteList() {
  const rows = await api('/api/quotes');
  view.innerHTML = `
    <div class="pagehead"><div>${svc('AI Negotiator', 'deal')}<h2>Open quotes</h2>
      <p>PDA quotes not yet approved, against what each port usually costs for the same vessel type and size.</p></div></div>
    <div class="tbl"><table>
      <tr><th>Vessel and port</th><th>Agent</th><th>Call</th><th class="num">Quoted</th><th>Above benchmark</th><th class="num">Potential saving</th><th></th></tr>
      ${rows.map(q => `<tr class="row" onclick="location.hash='#/negotiator/${q.proforma_id}'">
        <td><b>${esc(q.vessel_name)}</b><div class="exp">${esc(q.port_name)} · ${esc(q.vessel_type)}, ${esc(q.size_band)}</div></td>
        <td>${esc(q.agent_name)}<div class="exp">${esc(q.buyer_name)}</div></td><td class="nowrap">${month(q.call_month)}</td>
        <td class="num nowrap">${money(q.quoted_eur)}</td>
        <td>${q.flagged_lines ? `<span class="pill review">${q.flagged_lines} of ${q.lines} lines</span>` : '<span class="pill ok">None</span>'}</td>
        <td class="num nowrap amt-ok">${q.saving_eur ? money(q.saving_eur) : '-'}</td>
        <td>${q.has_draft ? '<span class="pill info">Draft saved</span>' : ''}</td></tr>`).join('')}
    </table></div>`;
}

async function quoteDetail(id) {
  const d = await api(`/api/quotes/${id}`); const q = d.quote;
  view.innerHTML = `
    <a class="back" href="#/negotiator">${I.back}All open quotes</a>
    <div class="pagehead"><div><h2>${esc(q.vessel_name)} at ${esc(q.port_name)}</h2>
      <p>PDA quote from ${esc(q.agent_name)} for ${esc(q.buyer_name)} · ${esc(q.vessel_type)}, ${esc(q.size_band)} · ${month(q.call_month)}</p></div>
      <span class="pill info">Open quote</span></div>
    <div class="grid g-main">
      <div class="card flush"><div class="head"><h3>${I.euro}Quote against the benchmark</h3>
        <div class="sub" style="margin:0">Benchmark: the median final cost of past calls, same port, vessel type and size first. Amounts in EUR.</div></div>
        <div class="tbl" style="border-radius:0;border-left:0;border-right:0;border-bottom:0"><table>
          <tr><th>Expense</th><th class="num">Quoted</th><th class="num">Benchmark</th><th class="num">Gap</th><th class="num">Saving</th></tr>
          ${d.lines.map(l => `<tr><td><b>${esc(l.expense_name)}</b>${l.flagged ? `<div class="exp">${esc(l.reasoning)}</div>` : ''}</td>
            <td class="num nowrap ${l.flagged ? 'amt-review' : ''}">${num(l.quoted_amount_eur)}</td>
            <td class="num nowrap">${l.benchmark_median_eur != null ? num(l.benchmark_median_eur) : '<span class="muted small">too few calls</span>'}${l.benchmark_sample_size ? `<div class="exp">${l.benchmark_sample_size} past calls</div>` : ''}</td>
            <td class="num nowrap">${l.gap_to_benchmark_pct != null ? `<span class="pill ${l.flagged ? 'review' : 'ok'}">${l.gap_to_benchmark_pct > 0 ? '+' : ''}${num(l.gap_to_benchmark_pct, 1)}%</span>` : ''}</td>
            <td class="num nowrap amt-ok">${l.flagged ? num(l.potential_saving_eur) : ''}</td></tr>`).join('')}
          <tr class="total"><td>Total</td><td class="num">${num(d.lines.reduce((a, l) => a + (l.quoted_amount_eur || 0), 0))}</td><td></td><td></td>
            <td class="num">${num(d.lines.filter(l => l.flagged).reduce((a, l) => a + (l.potential_saving_eur || 0), 0))}</td></tr>
        </table></div></div>
      <div class="grid">
        <div class="card"><div class="row-gap" style="justify-content:space-between"><h3>${I.deal}Negotiation email</h3>${svc('AI Negotiator', 'deal')}</div>
          <div class="sub">The agent reads the quote, the price history at this port and past competing quotes, then drafts the email. Every amount is checked against the data.</div>
          <div class="field"><label>Your instructions (optional)</label><input type="text" id="instr" placeholder="For example: keep it short, focus on pilotage and towage"></div>
          <button class="btn" id="draftbtn">${I.spark}Draft the email</button>
          <div id="draft"></div></div>
        ${d.drafts.length ? `<div class="card"><h3>${I.save}Saved drafts</h3>${d.drafts.map(x => `<div class="check"><span class="pill info">Draft</span><div><div class="n" style="text-transform:none">${esc(x.subject)}</div><div class="e">${esc(x.created_by)} · ${when(x.created_at)}</div></div></div>`).join('')}</div>` : ''}
      </div>
    </div>`;
  $('#draftbtn').onclick = async () => {
    const b = $('#draftbtn'); b.disabled = true;
    $('#draft').innerHTML = loading('Reading the quote, the price history and competing quotes');
    try { renderDraft(id, await api(`/api/quotes/${id}/draft`, { method: 'POST', body: { instructions: $('#instr').value } })); }
    catch (e) { $('#draft').innerHTML = `<div class="warn" style="margin-top:14px">${I.alert}${esc(e.message)}</div>`; }
    b.disabled = false; b.innerHTML = `${I.spark}Draft again`;
  };
}

function renderDraft(id, r) {
  const label = { get_quote: a => 'Read the quote', get_price_history: a => `Price history: ${a.expense_category} at ${a.port_name}`,
    get_competing_quotes: a => `Competing quotes: ${a.expense_category} at ${a.port_name}` };
  $('#draft').innerHTML = `
    <div class="steps">${r.steps.map(s => `<div class="step">${I.check}${esc((label[s.tool] || (() => s.tool))(s.args))} <span class="muted small">(${s.rows} rows)</span></div>`).join('')}</div>
    ${r.unverified_amounts.length ? `<div class="warn">${I.alert}<div><b>Check these amounts:</b> ${r.unverified_amounts.map(esc).join(', ')} were not found in the data the agent read.</div></div>`
      : `<div class="ok-note">${I.check}Every amount in the email was found in the data.</div>`}
    <div class="field" style="margin-top:14px"><label>Subject</label><input type="text" id="subj" value="${esc(r.subject)}"></div>
    <div class="field"><label>Email</label><textarea id="body" rows="16">${esc(r.body)}</textarea></div>
    <div class="actions"><button class="btn" id="savebtn">${I.save}Save draft</button><button class="btn ghost" id="copybtn">${I.copy}Copy</button></div>`;
  $('#copybtn').onclick = () => { navigator.clipboard.writeText(`${$('#subj').value}\n\n${$('#body').value}`); toast('Copied'); };
  $('#savebtn').onclick = async () => {
    const ok = await confirmBox({ title: 'Save this draft', text: 'The draft is saved with the quote so the team can send it. Nothing is sent to the agent.', ok: 'Save draft' });
    if (!ok) return;
    try { await api(`/api/quotes/${id}/drafts`, { method: 'POST', body: { ...r, subject: $('#subj').value, body: $('#body').value } }); toast('Draft saved'); }
    catch (e) { toast(e.message, true); }
  };
}

// ---------- port calls (DA Event Summarizer) ----------
async function portCallList() {
  const rows = await api('/api/fdas');
  view.innerHTML = `
    <div class="pagehead"><div>${svc('DA Event Summarizer', 'clock')}<h2>Port calls</h2>
      <p>Port calls with a statement of facts: the timeline read from the document, and a written account on demand.</p></div></div>
    <div class="grid g3">${rows.map(r => `
      <a class="pcard" href="#/port-calls/${r.port_call_id}">
        <div class="row-gap"><div class="ico">${I.ship}</div><div><div class="t">${esc(r.vessel_name)}</div><div class="s">${esc(r.port_name)} · ${month(r.call_month)}</div></div></div>
        <div class="s pa">${esc(r.agent_name)}</div>
        <div class="foot"><span class="muted small">Port call ${r.port_call_id}</span>${r.hold_payment ? '<span class="pill hold">Payment on hold</span>' : r.lines_flagged ? `<span class="pill review">${r.lines_flagged} lines to check</span>` : '<span class="pill ok">All lines match</span>'}</div>
      </a>`).join('')}</div>`;
}

async function portCall(id) {
  const d = await api(`/api/port-calls/${id}`); const pc = d.port_call;
  if (!pc) { view.innerHTML = '<div class="card">No such port call.</div>'; return; }
  const sof = d.documents.find(x => x.doc_type === 'statement_of_facts');
  const evs = d.events.map((e, i) => {
    const prev = d.events[i - 1]; let gap = '';
    if (prev && e.event_time && prev.event_time) {
      const h = (new Date(e.event_time) - new Date(prev.event_time)) / 36e5;
      if (h >= 3) gap = `<div class="gap">${num(h, 1)} hours</div>`;
    }
    return `${gap}<div class="ev"><div class="time">${e.event_time ? when(e.event_time) : esc(e.event_time_text)}</div><div class="what">${esc(e.event)}</div>
      <span class="pagechip" data-file="${e.file_item_id}" data-page="${e.page_number}">${I.page}p. ${e.page_number}</span></div>`;
  }).join('');
  view.innerHTML = `
    <a class="back" href="#/port-calls">${I.back}All port calls</a>
    <div class="pagehead"><div><h2>${esc(pc.vessel_name)} at ${esc(pc.port_name)}</h2>
      <p>${esc(pc.vessel_type)}, ${num(pc.gross_tonnage, 0)} GT · IMO ${esc(pc.imo)} · ${esc(pc.agent_name)} for ${esc(pc.buyer_name)}</p></div>
      ${pc.evaluation_id ? `<a class="btn ghost sm" href="#/review/${pc.evaluation_id}">${I.review}Final DA</a>` : ''}</div>
    <div class="card" style="margin-bottom:20px"><div class="facts">
      <div class="fact"><div class="k">Arrival</div><div class="v">${when(pc.schedule_date_in)}</div></div>
      <div class="fact"><div class="k">Departure</div><div class="v">${when(pc.schedule_date_out)}</div></div>
      <div class="fact"><div class="k">Port stay</div><div class="v">${num(pc.port_stay_hours, 1)} h</div></div>
      <div class="fact"><div class="k">Quoted</div><div class="v">${money(pc.quoted_amount, pc.currency)}</div></div>
      <div class="fact"><div class="k">Final</div><div class="v">${money(pc.final_amount, pc.currency)}</div></div>
      <div class="fact"><div class="k">FDA to approval</div><div class="v">${pc.fda_approval_hours != null ? num(pc.fda_approval_hours, 1) + ' h' : '-'}</div></div></div></div>
    <div class="grid g-main">
      <div class="grid">
        <div class="card"><div class="row-gap" style="justify-content:space-between"><h3>${I.clock}Timeline from the statement of facts</h3>${svc('DA Event Summarizer', 'clock')}</div>
          <div class="sub">${d.events.length ? `${d.events.length} events read from the document; click a page to see it.` : 'No statement of facts read yet.'}</div>
          <div class="timeline">${evs}</div></div>
        <div class="card"><h3>${I.spark}Written account</h3><div class="sub">Written on demand from the events above, with the page of each one.</div>
          <div id="story"><button class="btn" id="storybtn" ${d.events.length ? '' : 'disabled'}>${I.spark}Write the account</button></div></div>
      </div>
      <div class="card viewer"><div class="row-gap" style="justify-content:space-between;margin-bottom:12px"><h3>${I.page}Documents</h3>
        <div class="row-gap">${d.documents.map(x => `<span class="pagechip" data-file="${x.file_item_id}" data-page="1">${esc(DOC[x.doc_type] || x.doc_type)}</span>`).join('')}</div></div>
        <div id="pdf">${sof ? '' : '<div class="empty">No statement of facts received</div>'}</div></div>
    </div>`;
  const open = (file, page) => {
    $('#pdf').innerHTML = `<iframe title="Document" src="/api/documents/${file}?p=${page}#page=${page}&view=FitH"></iframe>`;
    view.querySelectorAll('.pagechip').forEach(c => c.classList.toggle('on', c.dataset.file === String(file) && c.dataset.page === String(page)));
  };
  const bind = () => view.querySelectorAll('.pagechip').forEach(c => c.onclick = () => open(c.dataset.file, c.dataset.page));
  bind(); if (sof) open(sof.file_item_id, 1);
  $('#storybtn').onclick = async () => {
    $('#story').innerHTML = loading('Writing the account');
    try {
      const r = await api(`/api/port-calls/${id}/story`, { method: 'POST' });
      $('#story').innerHTML = r.story ? `<div class="story">${md(r.story).replace(/\(p\. (\d+)\)/g, (m, n) => `<span class="pagechip" data-file="${sof.file_item_id}" data-page="${n}">${I.page}p. ${n}</span>`)}</div>`
        : `<div class="muted">${esc(r.reason)}</div>`;
      bind();
    } catch (e) { $('#story').innerHTML = `<div class="warn">${I.alert}${esc(e.message)}</div>`; }
  };
}

// ---------- HAL-9000 ----------
const chat = [];
async function hal() {
  const samples = ['Which ports have the highest cost per call?', 'Why are payments on hold?',
    'Which open quotes are above the benchmark?', 'What does the pilotage invoice of port call 20217 say?',
    'How long does FDA approval take by port?', 'Give me the timeline of port call 20400'];
  view.innerHTML = `
    <div class="pagehead"><div>${svc('HAL-9000', 'hal')}<h2>Ask HAL-9000</h2>
      <p>Routes each question to the right agent: port costs, DA audit, DA operations, or the documents themselves. Answers use your own data permissions.</p></div>
      <button class="btn ghost sm" id="newchat">New conversation</button></div>
    <div class="card chat"><div class="msgs" id="msgs"></div>
      <form class="composer" id="ask"><input name="q" placeholder="Ask about costs, DAs, payments, port calls or documents" autocomplete="off"><button class="btn">${I.send}Ask</button></form></div>`;
  const draw = () => {
    $('#msgs').innerHTML = chat.length ? chat.map(m => m.role === 'user' ? `<div class="msg user">${esc(m.content)}</div>`
      : `<div class="msg bot">${m.pending ? '<span class="typing"><i></i><i></i><i></i></span>' : md(m.content)}
          ${m.agents?.length ? `<div class="via">Answered with ${m.agents.map(a => `<span class="pill info">${esc(a)}</span>`).join('')}</div>` : ''}</div>`).join('')
      : `<div style="margin:auto;text-align:center"><div class="ico" style="margin:0 auto 12px;width:56px;height:56px">${I.hal}</div><div class="t">What would you like to know?</div>
          <div class="suggest">${samples.map(s => `<button type="button">${esc(s)}</button>`).join('')}</div></div>`;
    $('#msgs').scrollTop = 1e9;
    view.querySelectorAll('.suggest button').forEach(b => b.onclick = () => send(b.textContent));
  };
  const send = async q => {
    if (!q.trim()) return;
    chat.push({ role: 'user', content: q }); const bot = { role: 'assistant', pending: true, content: '' }; chat.push(bot); draw();
    try {
      const r = await api('/api/hal', { method: 'POST', body: { messages: chat.filter(m => !m.pending && m.content).map(({ role, content }) => ({ role, content })) } });
      Object.assign(bot, { pending: false, content: r.answer || 'No answer.', agents: r.agents });
    } catch (e) { Object.assign(bot, { pending: false, content: `Sorry, that failed: ${e.message}` }); }
    draw();
  };
  $('#ask').onsubmit = e => { e.preventDefault(); const q = e.target.q.value; e.target.q.value = ''; send(q); };
  $('#newchat').onclick = () => { chat.length = 0; draw(); };
  draw();
  if (sessionStorage.q) { const q = sessionStorage.q; delete sessionStorage.q; send(q); }
}

route();
