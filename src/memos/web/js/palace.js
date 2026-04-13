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

// ── Treemap Spatial View ──────────────────────────────────────────
let treemapVisible = false;

async function showTreemap(){
  treemapVisible = true;
  const container = document.getElementById('treemap-container');
  if(!container) return;
  container.textContent = '';
  // Load wings if not loaded
  if(!palaceData.wings.length){
    try{
      const wr = await fetch(API+'/palace/wings').then(r=>r.json());
      palaceData.wings = wr.wings||[];
    }catch(_){}
  }
  if(!palaceData.wings.length){
    container.innerHTML = '<div class="treemap-empty">No palace data. Run <code>memos palace-build</code>.</div>';
    return;
  }
  // Load rooms for each wing
  const wingData = [];
  let totalMemories = 0;
  for(const wing of palaceData.wings){
    const wName = wing.name||wing;
    try{
      const r = await fetch(API+'/palace/rooms?wing='+encodeURIComponent(wName)).then(res=>res.json());
      const rooms = r.rooms||[];
      let wingTotal = 0;
      const roomData = [];
      for(const room of rooms){
        const rName = room.name||room;
        // Get memories for this room
        let mems = [];
        try{
          const mr = await fetch(API+'/palace/recall?query=*&wing='+encodeURIComponent(wName)+'&room='+encodeURIComponent(rName)+'&top=50').then(res=>res.json());
          mems = mr.memories||[];
        }catch(_){}
        wingTotal += mems.length||room.memory_count||0;
        roomData.push({name:rName, count:mems.length||room.memory_count||0, memories:mems});
      }
      totalMemories += wingTotal;
      wingData.push({name:wName, rooms:roomData, count:wingTotal});
    }catch(_){
      wingData.push({name:wName, rooms:[], count:0});
    }
  }
  if(!totalMemories){
    container.innerHTML = '<div class="treemap-empty">No palace data. Run <code>memos palace-build</code>.</div>';
    return;
  }
  // Render treemap using flexbox layout
  const wingColors = ['#7c6ff722','#f9731622','#06b6d422','#22c55e22','#f43f5e22','#a855f722','#eab30822'];
  const wingBorders = ['#7c6ff744','#f9731644','#06b6d444','#22c55e44','#f43f5e44','#a855f744','#eab30844'];
  const wingAccents = ['#7c6ff7','#f97316','#06b6d4','#22c55e','#f43f5e','#a855f7','#eab308'];
  wingData.forEach((wing, wi) => {
    if(!wing.count) return;
    const wingEl = document.createElement('div');
    wingEl.className = 'treemap-wing';
    const pct = (wing.count / totalMemories * 100).toFixed(1);
    wingEl.style.flex = wing.count;
    wingEl.style.background = wingColors[wi%wingColors.length];
    wingEl.style.borderColor = wingBorders[wi%wingBorders.length];
    const header = document.createElement('div');
    header.className = 'treemap-wing-header';
    header.innerHTML = '<span style="color:'+wingAccents[wi%wingAccents.length]+';font-weight:600">'+escHtml(wing.name)+'</span> <span style="color:var(--text2);font-size:.8em">'+wing.count+' memories ('+pct+'%)</span>';
    wingEl.appendChild(header);
    // Rooms
    if(wing.rooms.length){
      const roomsEl = document.createElement('div');
      roomsEl.className = 'treemap-rooms';
      wing.rooms.forEach(room => {
        if(!room.count) return;
        const roomEl = document.createElement('div');
        roomEl.className = 'treemap-room';
        roomEl.style.flex = room.count;
        const roomHeader = document.createElement('div');
        roomHeader.className = 'treemap-room-header';
        roomHeader.textContent = room.name + ' (' + room.count + ')';
        roomEl.appendChild(roomHeader);
        // Memory leaves
        if(room.memories.length){
          const leafEl = document.createElement('div');
          leafEl.className = 'treemap-leaves';
          room.memories.slice(0, 20).forEach(mem => {
            const leaf = document.createElement('div');
            leaf.className = 'treemap-leaf';
            leaf.textContent = (mem.content||'').slice(0,30);
            leaf.title = mem.content||'';
            leaf.onclick = () => {
              // Show memory detail
              selId = mem.id;
              const fullNode = GD.nodes.find(n=>n.id===mem.id);
              if(fullNode) showMemoryDetail(fullNode);
              else {
                // Construct minimal node for display
                showMemoryDetail({id:mem.id, content:mem.content||'', tags:mem.tags||[], importance:mem.importance||0.5, age_days:mem.age_days||0, access_count:mem.access_count||0, namespace:mem.namespace||'default'});
              }
            };
            leafEl.appendChild(leaf);
          });
          roomEl.appendChild(leafEl);
        }
        roomsEl.appendChild(roomEl);
      });
      wingEl.appendChild(roomsEl);
    }
    container.appendChild(wingEl);
  });
}

function hideTreemap(){
  treemapVisible = false;
  const container = document.getElementById('treemap-container');
  if(container) container.style.display = 'none';
}
