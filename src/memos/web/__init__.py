"""Web dashboard for MemOS."""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MemOS Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; }
  .container { max-width: 960px; margin: 0 auto; padding: 20px; }
  h1 { text-align: center; margin-bottom: 20px; color: #7c6ff7; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .stat { background: #1a1a2e; border-radius: 8px; padding: 16px; text-align: center; }
  .stat .val { font-size: 1.8em; font-weight: bold; color: #7c6ff7; }
  .stat .lbl { font-size: 0.75em; color: #888; margin-top: 4px; }
  .panel { background: #1a1a2e; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .panel h2 { font-size: 1em; color: #7c6ff7; margin-bottom: 12px; }
  input, textarea, button { font-family: inherit; }
  input, textarea { width: 100%; padding: 8px; border: 1px solid #333; border-radius: 4px; background: #0f0f0f; color: #e0e0e0; margin-bottom: 8px; }
  button { background: #7c6ff7; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
  button:hover { background: #6a5ce0; }
  button.danger { background: #e74c3c; }
  .results { list-style: none; }
  .results li { background: #12122a; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
  .results li .score { color: #7c6ff7; font-weight: bold; }
  .results li .tags { color: #888; font-size: 0.8em; }
  .results li .meta { font-size: 0.75em; color: #555; margin-top: 4px; }
  .tags-input { font-size: 0.9em; }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1; }
</style>
</head>
<body>
<div class="container">
  <h1>🧠 MemOS Dashboard</h1>
  <div class="stats" id="stats"></div>

  <div class="panel">
    <h2>📝 Learn</h2>
    <textarea id="content" rows="3" placeholder="Enter memory content..."></textarea>
    <div class="row">
      <input id="tags" class="tags-input" placeholder="Tags (comma separated)">
      <input id="importance" type="number" min="0" max="1" step="0.1" value="0.5" placeholder="Importance">
    </div>
    <button onclick="doLearn()">Learn</button>
  </div>

  <div class="panel">
    <h2>🔍 Recall</h2>
    <input id="query" placeholder="Search query...">
    <div class="row">
      <input id="top" type="number" value="5" min="1" max="50" placeholder="Top K">
      <input id="filter_tags" placeholder="Filter tags (comma)">
    </div>
    <button onclick="doRecall()">Recall</button>
    <ul class="results" id="recall-results"></ul>
  </div>

  <div class="panel">
    <h2>⚙️ Prune</h2>
    <div class="row">
      <input id="prune_threshold" type="number" value="0.1" step="0.05" placeholder="Threshold">
      <input id="prune_max_age" type="number" value="90" placeholder="Max age (days)">
    </div>
    <button onclick="doPrune(false)">Dry Run</button>
    <button class="danger" onclick="doPrune(true)">Prune</button>
    <pre id="prune-result" style="margin-top:8px;color:#888;font-size:0.85em;"></pre>
  </div>
</div>

<script>
const API = '/api/v1';

async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  return res.json();
}

async function loadStats() {
  const s = await api('/stats');
  document.getElementById('stats').innerHTML = [
    ['total_memories', 'Memories'],
    ['total_tags', 'Tags'],
    ['avg_relevance', 'Avg Relevance'],
    ['avg_importance', 'Avg Importance'],
    ['decay_candidates', 'Decay Candidates'],
  ].map(([k, l]) => `<div class="stat"><div class="val">${s[k] ?? '—'}</div><div class="lbl">${l}</div></div>`).join('');
}

async function doLearn() {
  const content = document.getElementById('content').value.trim();
  if (!content) return;
  const tags = document.getElementById('tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const importance = parseFloat(document.getElementById('importance').value) || 0.5;
  await api('/learn', { method: 'POST', body: JSON.stringify({ content, tags, importance }) });
  document.getElementById('content').value = '';
  loadStats();
}

async function doRecall() {
  const query = document.getElementById('query').value.trim();
  if (!query) return;
  const top = parseInt(document.getElementById('top').value) || 5;
  const filter_tags = document.getElementById('filter_tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const data = await api('/recall', { method: 'POST', body: JSON.stringify({ query, top, filter_tags }) });
  const ul = document.getElementById('recall-results');
  ul.innerHTML = data.results.map(r => `<li>
    <span class="score">${r.score.toFixed(3)}</span> — ${r.content}
    <br><span class="tags">[${(r.tags||[]).join(', ')}]</span>
    <span class="meta">${r.age_days}d ago · ${r.match_reason}</span>
    <button class="danger" style="padding:2px 8px;font-size:0.7em;float:right" onclick="doForget('${r.id}')">🗑</button>
  </li>`).join('');
}

async function doForget(id) {
  await api('/memory/' + id, { method: 'DELETE' });
  loadStats();
  doRecall();
}

async function doPrune(forReal) {
  const threshold = parseFloat(document.getElementById('prune_threshold').value) || 0.1;
  const max_age_days = parseFloat(document.getElementById('prune_max_age').value) || 90;
  const data = await api('/prune', { method: 'POST', body: JSON.stringify({ threshold, max_age_days, dry_run: !forReal }) });
  document.getElementById('prune-result').textContent =
    (forReal ? 'Pruned' : 'Would prune') + `: ${data.pruned_count} memories` + (data.pruned_ids.length ? '\\nIDs: ' + data.pruned_ids.join(', ') : '');
  if (forReal) loadStats();
}

loadStats();
</script>
</body>
</html>"""
