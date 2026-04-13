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
function onLayerChange(v){
  layerFilter=v===''?null:parseInt(v);
  initGraph();
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

// ── Contradiction detection ────────────────────────────────────────
async function computeContradictions(){
  try{
    const facts=[];
    for(const label of ['EXTRACTED','INFERRED','AMBIGUOUS']){
      const r=await fetch(API+'/kg/labels?label='+label).then(res=>res.json());
      facts.push(...(r.facts||[]));
    }
    const groups={};
    facts.forEach(f=>{
      const key=(f.subject||'').toLowerCase()+'|'+(f.predicate||'').toLowerCase();
      if(!groups[key])groups[key]=[];
      groups[key].push(f);
    });
    const contradictions=[];
    Object.entries(groups).forEach(([key,fs])=>{
      const objects=new Set(fs.map(f=>(f.object||'').toLowerCase()));
      if(objects.size>1){
        contradictions.push({subject:fs[0].subject,predicate:fs[0].predicate,objects:[...objects],facts:fs});
      }
    });
    return contradictions;
  }catch(_){return [];}
}

// ── Health dashboard overlay ───────────────────────────────────────
async function showHealthDashboard(){
  const overlay=document.getElementById('health-overlay');
  if(!overlay)return;
  overlay.style.display='block';
  const content=document.getElementById('health-dashboard-content');
  content.textContent='Computing health metrics\u2026';
  const total=GD.nodes.length;
  const orphans=GD.nodes.filter(n=>(degreeMap[n.id]||0)===0);
  const stale=GD.nodes.filter(n=>(n.age_days||0)>30&&(n.access_count||0)===0);
  const kgNodes=new Set();
  GD.kgEdges.forEach(e=>{kgNodes.add(nid(e.source));kgNodes.add(nid(e.target));});
  const kgPct=total?((kgNodes.size/total)*100).toFixed(0):0;
  const contradictions=await computeContradictions();
  const healthScore=Math.max(0,Math.min(100,
    100-(orphans.length/Math.max(total,1)*50)-(stale.length/Math.max(total,1)*20)+(kgPct*0.3)-(contradictions.length*2)
  )).toFixed(0);
  const scoreColor=healthScore>=80?'#22c55e':healthScore>=50?'#eab308':'#e74c3c';
  // Age distribution buckets
  const ageBuckets=[0,0,0,0,0,0]; // <7d, 7-14d, 14-30d, 30-60d, 60-90d, 90d+
  GD.nodes.forEach(n=>{
    const d=n.age_days||0;
    if(d<7)ageBuckets[0]++;
    else if(d<14)ageBuckets[1]++;
    else if(d<30)ageBuckets[2]++;
    else if(d<60)ageBuckets[3]++;
    else if(d<90)ageBuckets[4]++;
    else ageBuckets[5]++;
  });
  const maxBucket=Math.max(...ageBuckets,1);
  const bucketLabels=['<7d','7-14d','14-30d','30-60d','60-90d','90d+'];
  const bucketColors=['#22c55e','#3b82f6','#7c6ff7','#f97316','#eab308','#64748b'];
  let ageChartHTML='<div class="health-age-chart">';
  ageBuckets.forEach((c,i)=>{
    const pct=(c/maxBucket*100).toFixed(0);
    ageChartHTML+=`<div class="health-age-bar-wrap"><div class="health-age-bar" style="height:${pct}%;background:${bucketColors[i]}"></div><span class="health-age-lbl">${bucketLabels[i]}</span></div>`;
  });
  ageChartHTML+='</div>';
  let html=`<div class="health-score-big" style="color:${scoreColor}">${healthScore}%</div>
    <div class="health-score-label">Overall Health</div>
    <div class="health-metrics-grid">
      <div class="health-metric-card"><div class="hmc-val">${total}</div><div class="hmc-lbl">Total memories</div></div>
      <div class="health-metric-card"><div class="hmc-val" style="color:${orphans.length?'#e74c3c':'#22c55e'}">${orphans.length}</div><div class="hmc-lbl">Orphans</div></div>
      <div class="health-metric-card"><div class="hmc-val" style="color:${stale.length>total*0.3?'#e74c3c':'#22c55e'}">${stale.length}</div><div class="hmc-lbl">Stale (>30d)</div></div>
      <div class="health-metric-card"><div class="hmc-val">${kgPct}%</div><div class="hmc-lbl">KG coverage</div></div>
      <div class="health-metric-card"><div class="hmc-val" style="color:${contradictions.length?'#f97316':'#22c55e'}">${contradictions.length}</div><div class="hmc-lbl">Contradictions</div></div>
    </div>`;
  if(orphans.length){
    html+='<div class="health-section"><h3>Orphan nodes</h3><div class="health-list">';
    orphans.slice(0,20).forEach(n=>{html+=`<span class="health-list-item" onclick="highlightNodeById('${n.id}')">${escHtml((n.content||'').slice(0,40))}</span>`;});
    if(orphans.length>20)html+=`<span class="health-list-more">\u2026 +${orphans.length-20} more</span>`;
    html+='</div></div>';
  }
  if(contradictions.length){
    html+='<div class="health-section"><h3>Contradictions</h3><div class="health-contradictions">';
    contradictions.slice(0,10).forEach(c=>{
      html+=`<div class="health-contradiction"><b>${escHtml(c.subject)}</b> \u2013${escHtml(c.predicate)}\u2192 <span style="color:#e74c3c">${c.objects.map(o=>escHtml(o)).join(' vs ')}</span></div>`;
    });
    html+='</div></div>';
  }
  html+=`<div class="health-section"><h3>Memory age distribution</h3>${ageChartHTML}</div>`;
  html+=`<button class="btn" style="background:var(--accent);color:#fff;margin-top:12px" onclick="suggestCleanup()">Suggest cleanup</button>`;
  content.innerHTML=html;
}

function closeHealthOverlay(){
  const overlay=document.getElementById('health-overlay');
  if(overlay)overlay.style.display='none';
}

function highlightNodeById(id){
  closeHealthOverlay();
  const node=GD.nodes.find(n=>n.id===id);
  if(!node)return;
  selId=id;focusNode=id;
  highlightNodes=new Set([id]);
  highlightLinks=new Set();
  if(fg){
    const data=fg.graphData();
    data.links.forEach(l=>{
      const s=nid(l.source),t=nid(l.target);
      if(s===id||t===id)highlightLinks.add(l);
    });
    fg.linkColor(fg.linkColor());fg.nodeColor(fg.nodeColor());
    if(node.x!==undefined)fg.centerAt(node.x,node.y,600);
  }
  showMemoryDetail(node);
}

function suggestCleanup(){
  closeHealthOverlay();
  const orphans=new Set(GD.nodes.filter(n=>(degreeMap[n.id]||0)===0).map(n=>n.id));
  const stale=new Set(GD.nodes.filter(n=>(n.age_days||0)>30&&(n.access_count||0)===0).map(n=>n.id));
  highlightNodes=new Set([...orphans,...stale]);
  highlightLinks=new Set();
  if(fg){fg.linkColor(fg.linkColor());fg.nodeColor(fg.nodeColor());}
}
