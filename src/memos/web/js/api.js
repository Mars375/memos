/* ── api.js ── API call functions ─────────────────────────────── */

async function fetchEntityExtra(entity) {
  const extra = document.getElementById('entity-extra');
  if (!extra) return;
  extra.textContent = 'Loading entity: ' + entity + '\u2026';
  try {
    const detail = await fetch(API + '/brain/entity/' + encodeURIComponent(entity)).then(r => r.json());
    if (detail.status !== 'ok') { extra.textContent = ''; return; }
    extra.textContent = '';
    const h = document.createElement('div'); h.className = 'entity-block';
    const htitle = document.createElement('h3'); htitle.textContent = 'Entity: ' + entity;
    h.appendChild(htitle); extra.appendChild(h);

    if ((detail.kg_facts || []).length) {
      const block = document.createElement('div'); block.className = 'entity-block';
      const t = document.createElement('h3'); t.textContent = 'KG facts'; block.appendChild(t);
      detail.kg_facts.forEach(f => {
        const row = document.createElement('div'); row.className = 'entity-fact';
        const subj = document.createElement('strong'); subj.textContent = f.subject || '';
        const pred = document.createElement('span');
        pred.style.cssText = 'color:var(--text2);font-style:italic';
        pred.textContent = ' \u2013' + (f.predicate || '') + '\u2192 ';
        const obj = document.createElement('strong'); obj.textContent = f.object || '';
        const meta = document.createElement('div');
        meta.className = 'entity-meta'; meta.textContent = f.confidence_label || 'EXTRACTED';
        row.appendChild(subj); row.appendChild(pred); row.appendChild(obj); row.appendChild(meta);
        block.appendChild(row);
      });
      extra.appendChild(block);
    }

    if ((detail.kg_neighbors || []).length) {
      const block = document.createElement('div'); block.className = 'entity-block';
      const t = document.createElement('h3'); t.textContent = 'Graph neighbors'; block.appendChild(t);
      detail.kg_neighbors.forEach(n => {
        const btn = document.createElement('button');
        btn.className = 'entity-link';
        btn.textContent = n.entity + ' (' + (n.relation_count || 0) + ')';
        btn.onclick = () => openEntityPanel(n.entity);
        block.appendChild(btn);
      });
      extra.appendChild(block);
    }
  } catch (_) { extra.textContent = ''; }
}

// Build KG edges: map KG entity names to node IDs by matching content/tags
function buildKGEdges(nodes, kgFacts) {
  // Build a lookup: entity name (lowercase) -> node id
  // Pass 1: tags first (canonical entity names)
  const entityToNode = {};
  nodes.forEach(n => {
    (n.tags || []).forEach(t => { entityToNode[t.toLowerCase()] = entityToNode[t.toLowerCase()] || n.id; });
  });
  // Pass 2: content words only for entities NOT already mapped by tags
  nodes.forEach(n => {
    const words = (n.content || '').match(/\b[A-Z][a-z]{2,}\b/g) || [];
    words.forEach(w => { entityToNode[w.toLowerCase()] = entityToNode[w.toLowerCase()] || n.id; });
  });
  // Pass 3: match KG entity names against node content substrings (case-insensitive)
  const factEntityNames = new Set();
  kgFacts.forEach(f => {
    if (f.subject) factEntityNames.add(f.subject.toLowerCase());
    if (f.object) factEntityNames.add(f.object.toLowerCase());
  });
  factEntityNames.forEach(entity => {
    if (entityToNode[entity]) return;
    for (const n of nodes) {
      if ((n.content || '').toLowerCase().includes(entity)) {
        entityToNode[entity] = entityToNode[entity] || n.id;
        break;
      }
    }
  });
  const edges = []; const seen = new Set();
  kgFacts.forEach(f => {
    const s = entityToNode[(f.subject || '').toLowerCase()];
    const t = entityToNode[(f.object || '').toLowerCase()];
    if (s && t && s !== t) {
      const key = [s, t].sort().join('|');
      if (!seen.has(key)) { seen.add(key); edges.push({ source: s, target: t, predicate: f.predicate, type: 'kg' }); }
    }
  });
  return edges;
}

async function loadWikiPagesList() {
  try {
    const r = await fetch(API + '/wiki/pages').then(res => res.json());
    wikiPages = r.pages || [];
    buildWikiSidebar();
    return wikiPages;
  } catch (_) { return []; }
}

async function loadWikiPage(nameOrSlug) {
  const content = document.getElementById('wiki-content');
  content.innerHTML = '<div style="color:var(--text2);padding:40px;text-align:center">Loading\u2026</div>';
  currentWikiPage = nameOrSlug;
  // Update breadcrumb
  document.getElementById('bc-sep').style.display = '';
  document.getElementById('bc-page').textContent = nameOrSlug;
  // Highlight in sidebar
  document.querySelectorAll('.wiki-page-item').forEach(el => el.classList.toggle('active', el.dataset.name === nameOrSlug));
  try {
    const slug = nameOrSlug.toLowerCase().replace(/\s+/g, '-');
    const r = await fetch(API + '/wiki/page/' + encodeURIComponent(slug)).then(res => res.json());
    if (r.status === 'not_found' || !r.content) {
      content.innerHTML = '<div id="wiki-empty">Page not found: <strong>' + escHtml(nameOrSlug) + '</strong></div>';
      return;
    }
    content.innerHTML = renderMarkdown(r.content);
  } catch (e) {
    content.innerHTML = '<div style="color:var(--danger);padding:40px">Error loading page.</div>';
  }
}

async function loadPalace() {
  try {
    const [wr, sr] = await Promise.all([
      fetch(API + '/palace/wings').then(r => r.json()),
      fetch(API + '/palace/stats').then(r => r.json()).catch(() => ({})),
    ]);
    palaceData.wings = wr.wings || [];
    buildPalaceTree(sr);
    document.getElementById('palace-count').textContent = palaceData.wings.length;
  } catch (_) { document.getElementById('palace-count').textContent = '0'; }
}

async function addMemory() {
  const content = document.getElementById('new-content').value.trim();
  if (!content) return;
  const tags = document.getElementById('new-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const ns = document.getElementById('new-ns').value.trim() || 'default';
  await fetch(API + '/learn', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, tags, namespace: ns, importance: .5 }) });
  document.getElementById('new-content').value = ''; document.getElementById('new-tags').value = ''; document.getElementById('new-ns').value = '';
  closeAddModal(); refreshGraph();
}

async function forgetSelected() {
  if (!selId) return;
  await fetch(API + '/memory/' + selId, { method: 'DELETE' });
  selId = null; closeRightPanel(); refreshGraph();
}

async function openKGOverlay(label) {
  document.getElementById('kg-overlay-title').textContent = label + ' Facts';
  const listEl = document.getElementById('kg-facts-list');
  listEl.textContent = 'Loading\u2026';
  document.getElementById('kg-facts-overlay').style.display = 'block';
  try {
    const r = await fetch(API + '/kg/labels?label=' + encodeURIComponent(label)).then(res => res.json());
    const facts = r.facts || [];
    listEl.textContent = '';
    if (!facts.length) { const e = document.createElement('span'); e.style.cssText = 'color:var(--text2);font-size:.8em'; e.textContent = 'No facts with this label.'; listEl.appendChild(e); return; }
    facts.forEach(f => {
      const row = document.createElement('div'); row.className = 'kgf-row';
      const subj = document.createElement('span'); subj.className = 'kgf-subj'; subj.textContent = f.subject || '';
      const pred = document.createElement('span'); pred.className = 'kgf-pred'; pred.textContent = '\u2013' + (f.predicate || '') + '\u2192';
      const obj = document.createElement('span'); obj.className = 'kgf-obj'; obj.textContent = f.object || '';
      row.appendChild(subj); row.appendChild(pred); row.appendChild(obj);
      if (f.source) { const src = document.createElement('span'); src.className = 'kgf-src'; src.textContent = f.source; row.appendChild(src); }
      listEl.appendChild(row);
    });
  } catch (_) { listEl.textContent = 'Error loading facts.'; }
}

// ── Task 5.1: Surprising connections ───────────────────────────
async function fetchSurprisingConnections(topK = 5) {
  try {
    const r = await fetch(API + '/kg/surprising?top_k=' + topK).then(res => res.json());
    return r.connections || [];
  } catch (_) { return []; }
}

// ── Task 5.2: Suggested questions ──────────────────────────────
async function fetchSuggestedQuestions(topK = 5) {
  try {
    const r = await fetch(API + '/brain/suggest?top_k=' + topK).then(res => res.json());
    return r.questions || [];
  } catch (_) { return []; }
}

// ── Task 5.3: Community detection ──────────────────────────────
async function fetchCommunities() {
  try {
    const r = await fetch(API + '/kg/communities').then(res => res.json());
    return r.communities || [];
  } catch (_) { return []; }
}

// ── Task 5.3: God nodes ───────────────────────────────────────
async function fetchGodNodes(topK = 10) {
  try {
    const r = await fetch(API + '/brain/god-nodes?top_k=' + topK).then(res => res.json());
    return r.nodes || [];
  } catch (_) { return []; }
}

async function openEntityPanel(entity) {
  const rp = document.getElementById('right-panel');
  document.getElementById('rp-title').textContent = entity;
  document.getElementById('rp-subtitle').textContent = 'Entity detail \u00b7 KG + Wiki';
  const body = document.getElementById('rp-body');
  body.textContent = 'Loading entity detail\u2026';
  rp.classList.add('open');
  try {
    const [detail, subgraph] = await Promise.all([
      fetch(API + '/brain/entity/' + encodeURIComponent(entity)).then(r => r.json()),
      fetch(API + '/brain/entity/' + encodeURIComponent(entity) + '/subgraph?depth=2').then(r => r.json()).catch(() => null),
    ]);
    if (detail.status !== 'ok') { body.textContent = 'Failed to load.'; return; }
    body.textContent = '';

    const sections = [
      { title: 'Community', content: detail.community || 'n/a', type: 'text' },
      { title: 'Wiki page', content: detail.wiki_page, type: 'pre' },
      { title: 'Top memories', items: detail.memories, type: 'memories' },
      { title: 'KG facts', items: detail.kg_facts, type: 'facts' },
      { title: 'Graph neighbors', items: detail.kg_neighbors, type: 'neighbors' },
      { title: 'Backlinks', items: detail.backlinks, type: 'backlinks' },
      { title: 'Subgraph', content: (subgraph && subgraph.status === 'ok') ? subgraph.nodes.length + ' nodes \u00b7 ' + subgraph.edges.length + ' edges' : 'Unavailable', type: 'text' },
    ];
    sections.forEach(sec => {
      if (sec.type === 'text' || (sec.type === 'pre' && sec.content)) {
        const block = document.createElement('div'); block.className = 'entity-block';
        const h = document.createElement('h3'); h.textContent = sec.title; block.appendChild(h);
        if (sec.type === 'pre') { const pre = document.createElement('div'); pre.className = 'entity-pre'; pre.textContent = sec.content; block.appendChild(pre); }
        else { const p = document.createElement('div'); p.textContent = sec.content; block.appendChild(p); }
        body.appendChild(block);
      } else if (sec.items && sec.items.length) {
        const block = document.createElement('div'); block.className = 'entity-block';
        const h = document.createElement('h3'); h.textContent = sec.title; block.appendChild(h);
        sec.items.forEach(item => {
          if (sec.type === 'memories') {
            const div = document.createElement('div'); div.className = 'entity-memory';
            const t = document.createElement('div'); t.textContent = item.content || ''; div.appendChild(t);
            const m = document.createElement('div'); m.className = 'entity-meta';
            m.textContent = 'importance ' + Number(item.importance || 0).toFixed(2) + ' \u00b7 ' + (item.source || 'memory');
            div.appendChild(m); block.appendChild(div);
          } else if (sec.type === 'facts') {
            const div = document.createElement('div'); div.className = 'entity-fact';
            const subj = document.createElement('strong'); subj.textContent = item.subject || '';
            const pred = document.createElement('span'); pred.style.cssText = 'color:var(--text2);font-style:italic';
            pred.textContent = ' \u2013' + (item.predicate || '') + '\u2192 ';
            const obj = document.createElement('strong'); obj.textContent = item.object || '';
            const meta = document.createElement('div'); meta.className = 'entity-meta';
            meta.textContent = item.confidence_label || 'EXTRACTED';
            div.appendChild(subj); div.appendChild(pred); div.appendChild(obj); div.appendChild(meta);
            block.appendChild(div);
          } else if (sec.type === 'neighbors') {
            const btn = document.createElement('button'); btn.className = 'entity-link';
            btn.textContent = item.entity + ' (' + (item.relation_count || 0) + ')';
            btn.onclick = () => openEntityPanel(item.entity); block.appendChild(btn);
          } else if (sec.type === 'backlinks') {
            const btn = document.createElement('button'); btn.className = 'entity-link';
            btn.textContent = item;
            btn.onclick = () => openEntityPanel(item); block.appendChild(btn);
          }
        });
        body.appendChild(block);
      }
    });
  } catch (_) { body.textContent = 'Error loading entity.'; }
}
