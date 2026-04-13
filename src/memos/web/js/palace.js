// ── palace.js — Memory Palace: load, build tree, highlight room ──

let palaceData = { wings: [], rooms: [] };
let activeRoom = null;

async function loadPalace() {
  try {
    const [wr, sr] = await Promise.all([
      fetch(API + '/palace/wings').then(r => r.json()),
      fetch(API + '/palace/stats').then(r => r.json()).catch(() => ({})),
    ]);
    palaceData.wings = wr.wings || [];
    buildPalaceTree(sr);
    document.getElementById('palace-count').textContent = palaceData.wings.length;
  } catch(_) { document.getElementById('palace-count').textContent = '0'; }
}

function buildPalaceTree(stats) {
  // Stats grid
  const sg = document.getElementById('palace-stats-grid');
  if (sg && stats) {
    sg.textContent = '';
    [['Wings', stats.total_wings || palaceData.wings.length], ['Rooms', stats.total_rooms || '?'], ['Assigned', stats.assigned_memories || '?']].forEach(([l, v]) => {
      const d = document.createElement('div'); d.className = 'palace-stat';
      const b = document.createElement('b'); b.textContent = v;
      d.appendChild(b); d.appendChild(document.createTextNode(l));
      sg.appendChild(d);
    });
  }
  // Wings tree
  const tree = document.getElementById('palace-wings-tree');
  if (!tree) return;
  tree.textContent = '';
  palaceData.wings.forEach(wing => {
    const wingRow = document.createElement('div'); wingRow.className = 'palace-wing';
    const header = document.createElement('div'); header.className = 'ft-row ft-leaf';
    const arrow = document.createElement('span'); arrow.className = 'arrow'; arrow.textContent = '\u25B6';
    const icon = document.createElement('span'); icon.className = 'ft-icon'; icon.textContent = '\uD83C\uDFDB';
    const label = document.createElement('span'); label.className = 'ft-label'; label.textContent = wing.name || wing;
    header.appendChild(arrow); header.appendChild(icon); header.appendChild(label);
    const roomsDiv = document.createElement('div'); roomsDiv.style.display = 'none';
    header.onclick = async () => {
      const open = roomsDiv.style.display !== 'none';
      roomsDiv.style.display = open ? 'none' : 'block';
      header.classList.toggle('open', !open);
      if (!open && !roomsDiv.children.length) {
        // Load rooms for this wing
        try {
          const r = await fetch(API + '/palace/rooms?wing=' + encodeURIComponent(wing.name || wing)).then(res => res.json());
          (r.rooms || []).forEach(room => {
            const roomRow = document.createElement('div'); roomRow.className = 'palace-room';
            const ri = document.createElement('span'); ri.textContent = '\uD83D\uDEAA '; ri.style.opacity = '.6';
            const rl = document.createElement('span'); rl.textContent = room.name || room;
            roomRow.appendChild(ri); roomRow.appendChild(rl);
            if (room.memory_count) {
              const rc = document.createElement('span'); rc.className = 'ft-count'; rc.style.marginLeft = 'auto'; rc.textContent = room.memory_count;
              roomRow.appendChild(rc);
            }
            roomRow.onclick = (e) => { e.stopPropagation(); highlightPalaceRoom(wing.name || wing, room.name || room, roomRow); };
            roomsDiv.appendChild(roomRow);
          });
        } catch(_) {}
      }
    };
    wingRow.appendChild(header); wingRow.appendChild(roomsDiv);
    tree.appendChild(wingRow);
  });
}

async function highlightPalaceRoom(wing, room, rowEl) {
  // Clear previous
  document.querySelectorAll('.palace-room').forEach(r => r.classList.remove('active'));
  if (activeRoom && activeRoom.wing === wing && activeRoom.room === room) {
    activeRoom = null;
    clearAll();
    return;
  }
  activeRoom = { wing, room };
  rowEl.classList.add('active');
  try {
    const r = await fetch(API + '/palace/recall?query=*&wing=' + encodeURIComponent(wing) + '&room=' + encodeURIComponent(room) + '&top=200').then(res => res.json());
    const ids = new Set((r.memories || []).map(m => m.id));
    if (ids.size) {
      highlightNodes = ids;
      highlightLinks = new Set();
      const data = fg ? fg.graphData() : { links: [] };
      data.links.forEach(l => {
        if (ids.has(nid(l.source)) && ids.has(nid(l.target))) highlightLinks.add(l);
      });
      if (fg) { fg.linkColor(fg.linkColor()); fg.nodeColor(fg.nodeColor()); }
    }
  } catch(_) {}
}
