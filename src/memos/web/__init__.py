"""Web dashboard for MemOS — Second Brain Graph View."""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MemOS — Second Brain</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg:#0d0d1a;--bg2:#13132a;--bg3:#1a1a35;--border:#2a2a4a;
    --accent:#7c6ff7;--accent2:#a78bfa;--text:#e2e2f0;--text2:#8888aa;--danger:#e74c3c;
  }
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden;display:flex;}
  #sidebar{width:300px;min-width:300px;height:100vh;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;z-index:10;}
  #sidebar-header{padding:16px;border-bottom:1px solid var(--border);flex-shrink:0;}
  #sidebar-header h1{font-size:1.1em;color:var(--accent2);letter-spacing:.05em;margin-bottom:10px;}
  #search-box{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:7px 10px;color:var(--text);font-size:.85em;outline:none;transition:border-color .2s;}
  #search-box:focus{border-color:var(--accent);}
  #stats-bar{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;}
  .stat-chip{background:var(--bg3);border-radius:6px;padding:8px 10px;text-align:center;}
  .stat-chip .val{font-size:1.3em;font-weight:700;color:var(--accent2);}
  .stat-chip .lbl{font-size:.65em;color:var(--text2);margin-top:2px;text-transform:uppercase;letter-spacing:.06em;}
  #tags-panel{padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;max-height:150px;overflow-y:auto;}
  #tags-panel h3{font-size:.7em;text-transform:uppercase;letter-spacing:.08em;color:var(--text2);margin-bottom:8px;}
  .tag-chip{display:inline-flex;align-items:center;gap:4px;background:var(--bg3);border:1px solid var(--border);border-radius:20px;padding:3px 9px;font-size:.75em;cursor:pointer;margin:2px;transition:all .15s;user-select:none;}
  .tag-chip:hover{border-color:var(--accent);}
  .tag-chip.active{background:var(--accent);border-color:var(--accent);color:#fff;}
  .dot{width:7px;height:7px;border-radius:50%;display:inline-block;}
  #analytics-panel{padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;}
  #analytics-panel h3{font-size:.7em;text-transform:uppercase;letter-spacing:.08em;color:var(--text2);margin-bottom:8px;}
  .analytics-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-bottom:10px;}
  .metric{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 10px;text-align:center;}
  .metric .val{display:block;font-size:1.05em;font-weight:700;color:var(--accent2);}
  .metric .lbl{display:block;font-size:.62em;color:var(--text2);text-transform:uppercase;letter-spacing:.06em;margin-top:2px;}
  #analytics-chart{width:100%;height:140px;}
  #detail-panel{flex:1;overflow-y:auto;padding:16px;}
  #detail-empty{color:var(--text2);font-size:.82em;text-align:center;margin-top:30px;line-height:1.7;}
  #detail-card{display:none;}
  #detail-card.visible{display:block;}
  .dc-content{background:var(--bg3);border-radius:8px;padding:12px;font-size:.85em;line-height:1.6;margin-bottom:10px;border-left:3px solid var(--accent);word-break:break-word;}
  .dc-tags{margin-bottom:10px;}
  .badge{display:inline-block;border-radius:20px;padding:2px 9px;font-size:.72em;margin:2px;font-weight:500;}
  .dc-meta{font-size:.72em;color:var(--text2);display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:12px;}
  .dc-meta span strong{color:var(--text);}
  .btn{display:inline-block;padding:6px 14px;border-radius:5px;border:none;font-size:.78em;cursor:pointer;font-family:inherit;transition:opacity .15s;}
  .btn:hover{opacity:.85;}
  .btn-primary{background:var(--accent);color:#fff;}
  .btn-danger{background:var(--danger);color:#fff;}
  #add-panel{padding:12px 16px;border-top:1px solid var(--border);flex-shrink:0;}
  #add-panel h3{font-size:.7em;text-transform:uppercase;letter-spacing:.08em;color:var(--text2);margin-bottom:8px;}
  #add-panel textarea,#add-panel input{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:5px;color:var(--text);font-family:inherit;font-size:.82em;padding:6px 9px;margin-bottom:6px;outline:none;resize:vertical;}
  #add-panel textarea:focus,#add-panel input:focus{border-color:var(--accent);}
  #graph-area{flex:1;position:relative;overflow:hidden;}
  #graph-svg{width:100%;height:100%;}
  .glink{stroke:#2e2e50;stroke-opacity:.8;}
  .glink.hi{stroke:var(--accent);stroke-opacity:1;}
  .glink.fd{opacity:.05;}
  .gnode circle{cursor:pointer;}
  .gnode.hi circle{stroke:#fff;stroke-width:2px;}
  .gnode.fd{opacity:.12;}
  #tt{position:absolute;background:var(--bg2);border:1px solid var(--border);border-radius:7px;padding:8px 12px;font-size:.78em;pointer-events:none;max-width:220px;line-height:1.5;display:none;z-index:100;box-shadow:0 4px 20px rgba(0,0,0,.6);}
  #loading{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:var(--text2);font-size:.9em;display:flex;flex-direction:column;align-items:center;gap:12px;}
  .spin{width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;}
  @keyframes spin{to{transform:rotate(360deg);}}
  #controls{position:absolute;top:12px;right:12px;display:flex;flex-direction:column;gap:6px;z-index:10;}
  .cb{width:34px;height:34px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:1em;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:border-color .15s;}
  .cb:hover{border-color:var(--accent);}
  ::-webkit-scrollbar{width:4px;}
  ::-webkit-scrollbar-track{background:transparent;}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px;}
</style>
</head>
<body>
<div id="sidebar">
  <div id="sidebar-header">
    <h1>&#129504; MemOS</h1>
    <input id="search-box" type="text" placeholder="Search memories&hellip;" oninput="onSearch(this.value)">
  </div>
  <div id="stats-bar">
    <div class="stat-chip"><div class="val" id="s-nodes">&#8212;</div><div class="lbl">Memories</div></div>
    <div class="stat-chip"><div class="val" id="s-tags">&#8212;</div><div class="lbl">Tags</div></div>
    <div class="stat-chip"><div class="val" id="s-edges">&#8212;</div><div class="lbl">Links</div></div>
    <div class="stat-chip"><div class="val" id="s-decay">&#8212;</div><div class="lbl">Decaying</div></div>
  </div>
  <div id="tags-panel">
    <h3>Filter by tag</h3>
    <div id="tags-list"></div>
  </div>
  <div id="analytics-panel">
    <h3>Recall analytics</h3>
    <div class="analytics-grid">
      <div class="metric"><span class="val" id="a-success">—</span><span class="lbl">Success</span></div>
      <div class="metric"><span class="val" id="a-p95">—</span><span class="lbl">p95 ms</span></div>
    </div>
    <canvas id="analytics-chart" height="140"></canvas>
  </div>
  <div id="detail-panel">
    <p id="detail-empty">Click a node to<br>inspect a memory</p>
    <div id="detail-card">
      <div class="dc-content" id="dc-content"></div>
      <div class="dc-tags" id="dc-tags"></div>
      <div class="dc-meta" id="dc-meta"></div>
      <button class="btn btn-danger" onclick="forgetSelected()">&#128465; Forget</button>
    </div>
  </div>
  <div id="add-panel">
    <h3>+ Add memory</h3>
    <textarea id="new-content" rows="2" placeholder="Memory content&hellip;"></textarea>
    <input id="new-tags" type="text" placeholder="Tags (comma separated)">
    <button class="btn btn-primary" onclick="addMemory()" style="width:100%">Learn</button>
  </div>
</div>
<div id="graph-area">
  <div id="loading"><div class="spin"></div>Loading graph&hellip;</div>
  <svg id="graph-svg"></svg>
  <div id="tt"></div>
  <div id="controls">
    <button class="cb" onclick="zoomIn()">+</button>
    <button class="cb" onclick="zoomOut()">&minus;</button>
    <button class="cb" onclick="resetZoom()">&#8857;</button>
    <button class="cb" onclick="refreshGraph()">&#8635;</button>
  </div>
</div>
<script>
const API='/api/v1';
const PAL=['#7c6ff7','#f97316','#06b6d4','#22c55e','#f43f5e','#a855f7','#eab308','#14b8a6','#ec4899','#64748b','#fb923c','#4ade80','#38bdf8','#c084fc','#fb7185'];
const tcmap={};let ci=0;
function tc(t){if(!tcmap[t])tcmap[t]=PAL[ci++%PAL.length];return tcmap[t];}
function nr(d){return 4+d.importance*10+Math.min(d.access_count*.5,6);}

let GD={nodes:[],edges:[]},sim,svg,zoom,lSel,nSel,selId=null,aTags=new Set(),sq='';
let analyticsChart=null;

function initGraph(){
  const area=document.getElementById('graph-area');
  const W=area.clientWidth,H=area.clientHeight;
  svg=d3.select('#graph-svg');svg.selectAll('*').remove();
  const defs=svg.append('defs');
  const fl=defs.append('filter').attr('id','gw');
  fl.append('feGaussianBlur').attr('stdDeviation','2.5').attr('result','b');
  const fm=fl.append('feMerge');
  fm.append('feMergeNode').attr('in','b');fm.append('feMergeNode').attr('in','SourceGraphic');
  const g=svg.append('g').attr('id','gg');
  zoom=d3.zoom().scaleExtent([.05,10]).on('zoom',e=>g.attr('transform',e.transform));
  svg.call(zoom).on('click',clearAll);
  lSel=g.append('g').selectAll('line').data(GD.edges).join('line').attr('class','glink')
    .attr('stroke-width',d=>Math.min(d.weight*.7+.4,2.5));
  nSel=g.append('g').selectAll('g').data(GD.nodes).join('g').attr('class','gnode')
    .call(d3.drag().on('start',ds).on('drag',dd).on('end',de))
    .on('click',(e,d)=>{e.stopPropagation();onNC(d);})
    .on('mouseenter',(e,d)=>showTT(e,d)).on('mouseleave',hideTT);
  nSel.append('circle').attr('r',d=>nr(d)).attr('fill',d=>tc(d.primary_tag))
    .attr('filter','url(#gw)').style('fill-opacity',.85);
  sim=d3.forceSimulation(GD.nodes)
    .force('link',d3.forceLink(GD.edges).id(d=>d.id).distance(75).strength(.35))
    .force('charge',d3.forceManyBody().strength(-160))
    .force('center',d3.forceCenter(W/2,H/2))
    .force('col',d3.forceCollide().radius(d=>nr(d)+5))
    .on('tick',()=>{
      lSel.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
          .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
      nSel.attr('transform',d=>'translate('+d.x+','+d.y+')');
    });
}

function ds(e,d){if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;}
function dd(e,d){d.fx=e.x;d.fy=e.y;}
function de(e,d){if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}

function showTT(e,d){
  const tt=document.getElementById('tt');
  tt.style.display='block';
  const labelEl=document.createElement('span');
  labelEl.style.fontWeight='bold';
  labelEl.textContent=d.label;
  tt.textContent='';
  tt.appendChild(labelEl);
  tt.appendChild(document.createElement('br'));
  (d.tags||[]).forEach(t=>{
    const s=document.createElement('span');
    s.style.color=tc(t);s.textContent='#'+t+' ';
    tt.appendChild(s);
  });
}
function hideTT(){document.getElementById('tt').style.display='none';}
document.getElementById('graph-area').addEventListener('mousemove',e=>{
  const tt=document.getElementById('tt');
  if(tt.style.display!=='block')return;
  const r=document.getElementById('graph-area').getBoundingClientRect();
  let x=e.clientX-r.left+14,y=e.clientY-r.top+14;
  if(x+230>r.width)x-=244;
  tt.style.left=x+'px';tt.style.top=y+'px';
});

function nid(x){return typeof x==='object'?x.id:x;}

function onNC(d){
  selId=d.id;
  document.getElementById('detail-empty').style.display='none';
  document.getElementById('detail-card').classList.add('visible');
  document.getElementById('dc-content').textContent=d.content;

  const dtags=document.getElementById('dc-tags');
  dtags.textContent='';
  (d.tags||[]).forEach(t=>{
    const b=document.createElement('span');
    b.className='badge';
    b.style.background=tc(t)+'22';b.style.color=tc(t);b.style.border='1px solid '+tc(t)+'44';
    b.textContent='#'+t;
    dtags.appendChild(b);
  });

  const dm=document.getElementById('dc-meta');
  dm.textContent='';
  [['Importance',(d.importance*100).toFixed(0)+'%'],['Age',d.age_days+'d'],
   ['Accessed',d.access_count+'\xd7'],['ID',d.id.slice(0,8)+'\u2026']].forEach(([l,v])=>{
    const s=document.createElement('span');
    const strong=document.createElement('strong');
    strong.textContent=l;
    s.appendChild(strong);s.appendChild(document.createElement('br'));
    s.appendChild(document.createTextNode(v));
    dm.appendChild(s);
  });

  const conn=new Set([d.id]);
  GD.edges.forEach(e=>{const s=nid(e.source),t=nid(e.target);if(s===d.id)conn.add(t);if(t===d.id)conn.add(s);});
  nSel.classed('hi',n=>n.id===d.id).classed('fd',n=>!conn.has(n.id));
  lSel.classed('hi',e=>{const s=nid(e.source),t=nid(e.target);return s===d.id||t===d.id;})
      .classed('fd',e=>{const s=nid(e.source),t=nid(e.target);return s!==d.id&&t!==d.id;});
}

function clearAll(){
  selId=null;
  if(nSel)nSel.classed('hi fd',false);
  if(lSel)lSel.classed('hi fd',false);
  document.getElementById('detail-card').classList.remove('visible');
  document.getElementById('detail-empty').style.display='block';
}

function onSearch(q){
  sq=q.toLowerCase().trim();
  if(!sq){if(nSel)nSel.classed('hi fd',false);if(lSel)lSel.classed('fd',false);return;}
  const m=new Set(GD.nodes.filter(d=>d.content.toLowerCase().includes(sq)||(d.tags||[]).some(t=>t.toLowerCase().includes(sq))).map(d=>d.id));
  nSel.classed('fd',d=>!m.has(d.id)).classed('hi',d=>m.has(d.id));
  lSel.classed('fd',true).classed('hi',false);
}

function buildTags(){
  const cnt={};
  GD.nodes.forEach(n=>(n.tags||[]).forEach(t=>cnt[t]=(cnt[t]||0)+1));
  const sorted=Object.entries(cnt).sort((a,b)=>b[1]-a[1]);
  const tl=document.getElementById('tags-list');
  tl.textContent='';
  sorted.forEach(([tag,c])=>{
    const sp=document.createElement('span');
    sp.className='tag-chip';sp.dataset.tag=tag;
    sp.onclick=()=>toggleTag(tag);
    const dot=document.createElement('span');
    dot.className='dot';dot.style.background=tc(tag);
    sp.appendChild(dot);
    sp.appendChild(document.createTextNode(tag+' '));
    const small=document.createElement('small');
    small.style.opacity='.6';small.textContent=c;
    sp.appendChild(small);
    tl.appendChild(sp);
  });
}

function renderAnalytics(summary){
  if(!summary)return;
  const success=summary.success||{};
  const latency=summary.latency||{};
  document.getElementById('a-success').textContent=((success.success_rate??0).toFixed(1))+'%';
  document.getElementById('a-p95').textContent=((latency.p95??0).toFixed(1));

  const points=summary.daily_activity||[];
  const canvas=document.getElementById('analytics-chart');
  if(!canvas||typeof Chart==='undefined')return;
  const labels=points.map(p=>(p.date||'').slice(5));
  const values=points.map(p=>p.count||0);
  if(analyticsChart)analyticsChart.destroy();
  analyticsChart=new Chart(canvas.getContext('2d'),{
    type:'line',
    data:{labels,datasets:[{label:'Recalls',data:values,borderColor:'#7c6ff7',backgroundColor:'rgba(124,111,247,.18)',tension:.35,fill:true,pointRadius:1}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#8888aa',maxTicksLimit:6},grid:{color:'rgba(42,42,74,.35)'}},y:{ticks:{color:'#8888aa',precision:0},grid:{color:'rgba(42,42,74,.35)'}}}}
  });
}

function toggleTag(tag){
  const el=document.querySelector('.tag-chip[data-tag="'+tag+'"]');
  if(aTags.has(tag)){aTags.delete(tag);el.classList.remove('active');}
  else{aTags.add(tag);el.classList.add('active');}
  if(!aTags.size){if(nSel)nSel.classed('fd hi',false);if(lSel)lSel.classed('fd',false);return;}
  const m=new Set(GD.nodes.filter(d=>(d.tags||[]).some(t=>aTags.has(t))).map(d=>d.id));
  nSel.classed('fd',d=>!m.has(d.id)).classed('hi',false);
  lSel.classed('fd',e=>!m.has(nid(e.source))||!m.has(nid(e.target)));
}

function zoomIn(){svg.transition().call(zoom.scaleBy,1.4);}
function zoomOut(){svg.transition().call(zoom.scaleBy,.7);}
function resetZoom(){svg.transition().call(zoom.transform,d3.zoomIdentity);}

async function addMemory(){
  const content=document.getElementById('new-content').value.trim();
  if(!content)return;
  const rawTags=document.getElementById('new-tags').value;
  const tags=rawTags.split(',').map(t=>t.trim()).filter(Boolean);
  await fetch(API+'/learn',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({content,tags,importance:.5})});
  document.getElementById('new-content').value='';
  document.getElementById('new-tags').value='';
  refreshGraph();
}

async function forgetSelected(){
  if(!selId)return;
  await fetch(API+'/memory/'+selId,{method:'DELETE'});
  selId=null;
  document.getElementById('detail-card').classList.remove('visible');
  document.getElementById('detail-empty').style.display='block';
  refreshGraph();
}

async function refreshGraph(){
  document.getElementById('loading').style.display='flex';
  try{
    const [gd,st,an]=await Promise.all([
      fetch(API+'/graph').then(r=>r.json()),
      fetch(API+'/stats').then(r=>r.json()),
      fetch(API+'/analytics/summary?days=14').then(r=>r.json()).catch(()=>null)
    ]);
    GD={nodes:gd.nodes,edges:gd.edges};
    document.getElementById('s-nodes').textContent=gd.meta.total_nodes;
    document.getElementById('s-tags').textContent=gd.meta.total_tags;
    document.getElementById('s-edges').textContent=gd.meta.total_edges;
    document.getElementById('s-decay').textContent=st.decay_candidates??0;
    renderAnalytics(an);
    buildTags();initGraph();
  }finally{
    document.getElementById('loading').style.display='none';
  }
}

refreshGraph();
setInterval(refreshGraph,60000);
</script>
</body>
</html>"""
