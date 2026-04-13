/* ── utils.js ── Utility / helper functions ───────────────────── */

function tc(t) { if (!tcmap[t]) tcmap[t] = PAL[ci++ % PAL.length]; return tcmap[t]; }

function escHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function nid(x) { return typeof x === 'object' ? x.id : x; }

function extractEntitiesFromNode(d) {
  const seen = new Set(); const out = [];
  const add = v => { const s = (v || '').trim(); if (!s || s.length < 3) return; const k = s.toLowerCase(); if (!seen.has(k)) { seen.add(k); out.push(s); } };
  (d.tags || []).filter(t => /[A-Z]/.test(t)).forEach(add);
  ((d.content || '').match(/\b(?:[A-Z][\w-]*(?:\s+[A-Z][\w-]*)+|[A-Z][a-z]{3,})\b/g) || []).forEach(add);
  return out.slice(0, 5);
}
