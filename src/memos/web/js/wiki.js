/* ── wiki.js ── Wiki view ─────────────────────────────────────── */

function buildWikiSidebar() {
  const tl = document.getElementById('tags-children');
  // Also inject wiki pages into sidebar file tree when in wiki mode? No - use search bar.
}

function renderMarkdown(md) {
  if (!md) return '';
  // Process code blocks first (protect from other replacements)
  const codeBlocks = [];
  md = md.replace(/```([\s\S]*?)```/g, (_, code) => {
    const i = codeBlocks.length;
    codeBlocks.push('<pre><code>' + escHtml(code.trim()) + '</code></pre>');
    return '\x00CODE' + i + '\x00';
  });
  // Inline code
  md = md.replace(/`([^`\n]+)`/g, (_, c) => '<code>' + escHtml(c) + '</code>');
  // Headers
  md = md.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  md = md.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  md = md.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold/italic
  md = md.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  md = md.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // HR
  md = md.replace(/^---+$/gm, '<hr>');
  // Wikilinks [[Entity]] → clickable
  md = md.replace(/\[\[([^\]]+)\]\]/g, (_, name) =>
    '<a class="wiki-link" onclick="loadWikiPage(' + JSON.stringify(name) + ')">' + escHtml(name) + '</a>'
  );
  // Markdown links [text](url)
  md = md.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent2)">$1</a>');
  // Bullet lists
  const lines = md.split('\n');
  const out = [];
  let inList = false;
  for (const line of lines) {
    if (/^[\s]*[-*+] (.+)$/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push('<li>' + line.replace(/^[\s]*[-*+] /, '') + '</li>');
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      if (line.startsWith('<h') || line.startsWith('<hr') || line.startsWith('<pre') || line.startsWith('\x00CODE')) {
        out.push(line);
      } else if (line.trim()) {
        out.push('<p>' + line + '</p>');
      }
    }
  }
  if (inList) out.push('</ul>');
  md = out.join('\n');
  // Restore code blocks
  codeBlocks.forEach((block, i) => { md = md.replace('\x00CODE' + i + '\x00', block); });
  return md;
}

function goWikiHome() {
  currentWikiPage = null;
  document.getElementById('bc-sep').style.display = 'none';
  document.getElementById('bc-page').textContent = '';
  document.querySelectorAll('.wiki-page-item').forEach(el => el.classList.remove('active'));
  const content = document.getElementById('wiki-content');
  if (!wikiPages.length) {
    content.innerHTML = '<div id="wiki-empty">\uD83D\uDCD6 No wiki pages yet.<br>Run <code>memos wiki-compile</code> or add memories with compounding ingest enabled.</div>';
    return;
  }
  // Show page list
  content.textContent = '';
  const h = document.createElement('h1'); h.textContent = 'Living Wiki \u2014 ' + wikiPages.length + ' pages'; content.appendChild(h);
  const grid = document.createElement('div'); grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:16px';
  wikiPages.forEach(p => {
    const card = document.createElement('div');
    card.style.cssText = 'background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px;cursor:pointer';
    card.onmouseenter = () => card.style.borderColor = 'var(--accent)';
    card.onmouseleave = () => card.style.borderColor = 'var(--border)';
    const title = document.createElement('div');
    title.style.cssText = 'font-size:.85em;font-weight:600;color:var(--accent2);margin-bottom:4px';
    title.textContent = p.name;
    const meta = document.createElement('div');
    meta.style.cssText = 'font-size:.7em;color:var(--text2)';
    meta.textContent = (p.memory_count || 0) + ' memories';
    card.appendChild(title); card.appendChild(meta);
    card.onclick = () => loadWikiPage(p.name);
    grid.appendChild(card);
  });
  content.appendChild(grid);
}

function buildWikiPageList() {
  const tl = document.getElementById('tags-children');
  // Build wiki pages list in sidebar (shown when wiki mode active)
  const wikiList = document.getElementById('wiki-sidebar-list');
  if (!wikiList) return;
  wikiList.textContent = '';
  wikiPages.forEach(p => {
    const row = document.createElement('div');
    row.className = 'ft-row ft-leaf wiki-page-item'; row.dataset.name = p.name;
    row.onclick = () => loadWikiPage(p.name);
    const icon = document.createElement('span'); icon.className = 'ft-icon'; icon.textContent = '\uD83D\uDCDD';
    const label = document.createElement('span'); label.className = 'ft-label'; label.textContent = p.name;
    const count = document.createElement('span'); count.className = 'ft-count'; count.textContent = p.memory_count || '';
    row.appendChild(icon); row.appendChild(label); row.appendChild(count);
    wikiList.appendChild(row);
  });
}

function onWikiSearch(q) {
  clearTimeout(wikiSearchTimeout);
  const results = document.getElementById('wiki-search-results');
  if (!q.trim()) { results.style.display = 'none'; return; }
  wikiSearchTimeout = setTimeout(async () => {
    try {
      const r = await fetch(API + '/wiki/search?q=' + encodeURIComponent(q)).then(res => res.json());
      const hits = r.results || [];
      results.textContent = '';
      if (!hits.length) { results.style.display = 'none'; return; }
      hits.slice(0, 8).forEach(h => {
        const row = document.createElement('div'); row.className = 'wiki-search-result';
        const name = document.createElement('strong'); name.style.color = 'var(--accent2)'; name.textContent = h.entity || h.name || '';
        const snip = document.createElement('div'); snip.style.cssText = 'color:var(--text2);font-size:.75em;margin-top:2px';
        snip.textContent = (h.snippet || '').slice(0, 80);
        row.appendChild(name); row.appendChild(snip);
        row.onclick = () => { loadWikiPage(h.entity || h.name); results.style.display = 'none'; document.getElementById('wiki-search-bar').value = ''; };
        results.appendChild(row);
      });
      results.style.display = 'block';
    } catch (_) {}
  }, 300);
}

function showWikiSearchResults() {
  const r = document.getElementById('wiki-search-results');
  if (r.children.length) r.style.display = 'block';
}

// Close wiki search results on outside click
document.addEventListener('click', e => {
  const r = document.getElementById('wiki-search-results');
  if (r && !r.contains(e.target) && e.target.id !== 'wiki-search-bar') r.style.display = 'none';
});

async function wikiRefresh() {
  await loadWikiPagesList();
  if (currentWikiPage) loadWikiPage(currentWikiPage);
  else goWikiHome();
}
