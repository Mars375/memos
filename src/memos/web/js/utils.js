// ── utils.js — Helper functions: tc, escHtml, nid, nr ──

const tcmap={};let ci=0;
function tc(t){if(!tcmap[t])tcmap[t]=PAL[ci++%PAL.length];return tcmap[t];}
function escHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function nid(x){return typeof x==='object'?x.id:x;}

// ── Node radius from degree + importance ─────────────────────────
function nr(d){
  const deg=degreeMap[d.id]||0;
  if(deg>=10)return 10;
  if(deg>=6)return 7;
  if(deg>=3)return 5;
  return 3+(d.importance||0.5)*2;
}
