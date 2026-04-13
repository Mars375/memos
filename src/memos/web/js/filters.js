// ── filters.js — Clustering, filtering, search, health panel ──

const CLUSTER_PALETTE=[
  '#a78bfa','#34d399','#f59e0b','#60a5fa','#f472b6',
  '#2dd4bf','#fb923c','#818cf8','#4ade80','#fbbf24',
  '#38bdf8','#e879f9'
];
function detectClusters(){
  const adj={};
  GD.nodes.forEach(n=>{adj[n.id]=new Set();});
  const allE=[...GD.edges,...GD.kgEdges];
  allE.forEach(e=>{
    const s=nid(e.source),t=nid(e.target);
    if(adj[s])adj[s].add(t);
    if(adj[t])adj[t].add(s);
  });
  // BFS connected components
  const visited=new Set();
  let cid=0;
  GD.nodes.forEach(n=>{
    if(visited.has(n.id))return;
    const comp=[];
    const queue=[n.id];
    visited.add(n.id);
    while(queue.length){
      const cur=queue.shift();
      comp.push(cur);
      (adj[cur]||[]).forEach(nb=>{
        if(!visited.has(nb)){visited.add(nb);queue.push(nb);}
      });
    }
    const color=CLUSTER_PALETTE[cid%CLUSTER_PALETTE.length];
    comp.forEach(id=>{
      clusterMap[id]=cid;
      clusterColors[cid]=color;
    });
    cid++;
  });
}

// ── P1: BFS depth-limited neighborhood ──────────────────────────
function bfsNeighbors(startId, maxHops){
  if(maxHops<=0||!fg)return new Set(GD.nodes.map(n=>n.id));
  const data=fg.graphData();
  const adj={};
  GD.nodes.forEach(n=>{adj[n.id]=[];});
  data.links.forEach(l=>{
    const s=nid(l.source),t=nid(l.target);
    if(!adj[s])adj[s]=[];
    if(!adj[t])adj[t]=[];
    adj[s].push(t);
    adj[t].push(s);
  });
  const visited=new Set([startId]);
  const queue=[{id:startId,hop:0}];
  while(queue.length){
    const{id,hop}=queue.shift();
    if(hop>=maxHops)continue;
    (adj[id]||[]).forEach(nb=>{
      if(!visited.has(nb)){
        visited.add(nb);
        queue.push({id:nb,hop:hop+1});
      }
    });
  }
  return visited;
}

// ── Filter controls ──────────────────────────────────────────────
function onEdgeWeightChange(v){
  minEdgeWeight=parseInt(v);
  document.getElementById('edge-weight-val').textContent=v;
  initGraph();
}
function onDegreeChange(v){
  minDegree=parseInt(v);
  document.getElementById('degree-val').textContent=v;
  initGraph();
}
function onDepthChange(v){
  depthLimit=parseInt(v);
  document.getElementById('depth-val').textContent=v==='0'?'∞':v;
  if(fg&&focusNode){
    // Apply depth filter around focus node
    const neighbors=bfsNeighbors(focusNode,depthLimit);
    highlightNodes=neighbors;
    fg.nodeColor(fg.nodeColor());
  }
}
function onColorModeChange(v){
  colorMode=v;
  if(fg){
    fg.nodeColor(fg.nodeColor());
    fg.nodeCanvasObject(fg.nodeCanvasObject());
  }
}
function computeTimeRange(){
  const nodes=GD.nodes;
  if(!nodes.length){timeRange=[0,100];return;}
  const times=nodes.map(n=>new Date(n.created_at||0).getTime()).filter(t=>t>0);
  if(!times.length){timeRange=[0,100];return;}
  timeRange=[Math.min(...times),Math.max(...times)];
}
function onTimeChange(v){
  timePct=parseInt(v);
  const label=document.getElementById('time-val');
  if(timePct>=100){label.textContent='All';initGraph();return;}
  // Compute cutoff timestamp
  const span=timeRange[1]-timeRange[0]||1;
  const cutoff=timeRange[0]+(span*timePct/100);
  const cutoffDate=new Date(cutoff);
  label.textContent=cutoffDate.toLocaleDateString('en',{month:'short',day:'numeric'});
  // Rebuild graph with only nodes created before cutoff
  initGraph();
}
function shouldShowNode(n){
  if(timePct>=100)return true;
  const t=new Date(n.created_at||0).getTime();
  const span=timeRange[1]-timeRange[0]||1;
  const cutoff=timeRange[0]+(span*timePct/100);
  return t<=cutoff;
}
function updateHealthPanel(){
  const el=document.getElementById('health-stats');
  if(!el||!GD.nodes.length)return;
  const total=GD.nodes.length;
  // Orphans: nodes with 0 connections
  const orphans=GD.nodes.filter(n=>(degreeMap[n.id]||0)===0).length;
  // Average degree
  const avgDeg=(Object.values(degreeMap).reduce((a,b)=>a+b,0)/total).toFixed(1);
  // Average importance
  const avgImp=(GD.nodes.reduce((a,n)=>a+(n.importance||0),0)/total).toFixed(2);
  // Stale nodes (age > 30 days)
  const stale=GD.nodes.filter(n=>(n.age_days||0)>30).length;
  // KG coverage
  const kgNodes=new Set();
  GD.kgEdges.forEach(e=>{kgNodes.add(nid(e.source));kgNodes.add(nid(e.target));});
  const kgPct=((kgNodes.size/total)*100).toFixed(0);
  // Health score (simple heuristic)
  const healthScore=Math.max(0,Math.min(100,
    100 - (orphans/total*50) - (stale/total*20) + (kgPct*0.3)
  )).toFixed(0);
  const emoji=healthScore>=80?'🟢':healthScore>=50?'🟡':'🔴';
  el.innerHTML=
    emoji+' Health: <b>'+healthScore+'%</b><br>'+
    '📦 Total: <b>'+total+'</b> memories<br>'+
    '🔗 Avg degree: <b>'+avgDeg+'</b><br>'+
    '⭐ Avg importance: <b>'+avgImp+'</b><br>'+
    '🏝 Orphans: <b>'+(orphans||'<span style="color:#34d399">0</span>')+'</b><br>'+
    '⏰ Stale (&gt;30d): <b>'+stale+'</b><br>'+
    '🧠 KG coverage: <b>'+kgPct+'%</b>';
}
function toggleNSFilter(ns){
  if(activeNS.has(ns))activeNS.delete(ns);else activeNS.add(ns);
  // Update chip UI
  document.querySelectorAll('.ns-chip').forEach(c=>{
    c.classList.toggle('active',activeNS.has(c.dataset.ns));
  });
  initGraph();
}
function buildNSChips(){
  const nsSet=new Set(GD.nodes.map(n=>n.namespace||'default'));
  const container=document.getElementById('ns-chips');
  container.textContent='';
  nsSet.forEach(ns=>{
    const chip=document.createElement('span');
    chip.className='ns-chip';
    chip.dataset.ns=ns;
    chip.textContent=ns;
    chip.onclick=()=>toggleNSFilter(ns);
    container.appendChild(chip);
  });
}

// ── Search ───────────────────────────────────────────────────────
function onSearch(q){
  sq=q.toLowerCase().trim();
  if(!sq){clearAll();return;}
  const m=new Set(GD.nodes.filter(d=>
    (d.content||'').toLowerCase().includes(sq)||
    (d.tags||[]).some(t=>t.toLowerCase().includes(sq))
  ).map(d=>d.id));
  highlightNodes=m;
  highlightLinks=new Set();
  // Find links between matching nodes
  const data=fg?fg.graphData():{links:[]};
  data.links.forEach(l=>{
    if(m.has(nid(l.source))&&m.has(nid(l.target)))highlightLinks.add(l);
  });
  if(fg){
    fg.linkColor(fg.linkColor());
    fg.nodeColor(fg.nodeColor());
  }
  // Zoom to first match
  if(m.size>0&&fg){
    const first=GD.nodes.find(n=>m.has(n.id));
    if(first&&first.x!==undefined)fg.centerAt(first.x,first.y,600);
  }
}

function applyFilters(){
  // Filters are now handled by buildGraphData() called in initGraph()
  // This is kept for compatibility with tag tree clicks
}
