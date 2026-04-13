// ── sidebar.js — Tag tree, NS tree, KG labels, analytics ──

function buildTagTree(){
  const cnt={};
  GD.nodes.forEach(n=>(n.tags||[]).forEach(t=>cnt[t]=(cnt[t]||0)+1));
  const sorted=Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,60);
  const tl=document.getElementById('tags-children');
  tl.textContent='';
  sorted.forEach(([tag,c])=>{
    const row=document.createElement('div');
    row.className='ft-row ft-leaf';row.dataset.tag=tag;
    row.onclick=()=>toggleTag(tag);
    const icon=document.createElement('span');
    icon.className='ft-icon';icon.style.color=tc(tag);icon.textContent='\u25cf';
    const label=document.createElement('span');
    label.className='ft-label';label.textContent='#'+tag;
    const count=document.createElement('span');
    count.className='ft-count';count.textContent=c;
    row.appendChild(icon);row.appendChild(label);row.appendChild(count);
    tl.appendChild(row);
  });
  document.getElementById('tags-count').textContent=sorted.length;
}

async function buildNSTree(){
  let ns=[];
  try{
    const r=await fetch(API+'/ns/stats').then(res=>res.json());
    ns=r.namespaces||[];
  }catch(_){
    const m={};GD.nodes.forEach(n=>{const k=n.namespace||'default';m[k]=(m[k]||0)+1;});
    ns=Object.entries(m).map(([name,count])=>({name,count}));
  }
  const tl=document.getElementById('ns-children');
  tl.textContent='';
  ns.forEach(({name,count})=>{
    const row=document.createElement('div');
    row.className='ft-row ft-leaf';row.dataset.ns=name;
    row.onclick=()=>toggleNS(name);
    const icon=document.createElement('span');
    icon.className='ft-icon';icon.textContent=name==='default'?'\uD83D\uDCC1':'\uD83D\uDCC2';
    const label=document.createElement('span');
    label.className='ft-label';label.textContent=name;
    const countEl=document.createElement('span');
    countEl.className='ft-count';countEl.textContent=count||0;
    row.appendChild(icon);row.appendChild(label);row.appendChild(countEl);
    tl.appendChild(row);
  });
  document.getElementById('ns-count').textContent=ns.length;
}

async function loadKGLabels(){
  try{
    const r=await fetch(API+'/kg/labels').then(res=>res.json());
    const stats=r.label_stats||{};
    const container=document.getElementById('kg-children');
    container.textContent='';
    [{key:'EXTRACTED',cls:'lc-extracted',icon:'\u2295'},{key:'INFERRED',cls:'lc-inferred',icon:'\u21e2'},{key:'AMBIGUOUS',cls:'lc-ambiguous',icon:'~'}].forEach(({key,cls,icon})=>{
      const wrap=document.createElement('div');wrap.className='ft-row ft-leaf';
      const chip=document.createElement('span');chip.className='label-chip '+cls;
      chip.textContent=icon+' '+key+' ';
      const cnt=document.createElement('span');cnt.className='lc-count';cnt.textContent=String(stats[key]||0);
      chip.appendChild(cnt);wrap.appendChild(chip);
      wrap.onclick=()=>openKGOverlay(key);
      container.appendChild(wrap);
    });
  }catch(_){}
}

function toggleTag(tag){
  // Use search highlight instead of D3 class manipulation
  const m=new Set(GD.nodes.filter(d=>(d.tags||[]).includes(tag)).map(d=>d.id));
  highlightNodes=m;
  highlightLinks=new Set();
  const data=fg?fg.graphData():{links:[]};
  data.links.forEach(l=>{
    if(m.has(nid(l.source))&&m.has(nid(l.target)))highlightLinks.add(l);
  });
  if(fg){fg.linkColor(fg.linkColor());fg.nodeColor(fg.nodeColor());}
}
function toggleNS(ns){
  toggleNSFilter(ns);
}

function renderAnalytics(summary){
  if(!summary)return;
  const success=summary.success||{};const latency=summary.latency||{};
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
    data:{labels,datasets:[{label:'Recalls',data:values,borderColor:'#7c6ff7',backgroundColor:'rgba(124,111,247,.15)',tension:.35,fill:true,pointRadius:1}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#4e5370',maxTicksLimit:6},grid:{color:'rgba(30,33,56,.6)'}},y:{ticks:{color:'#4e5370',precision:0},grid:{color:'rgba(30,33,56,.6)'}}}}
  });
}

function toggleFT(childId,rowId){
  const ch=document.getElementById(childId);const row=document.getElementById(rowId);
  if(!ch)return;ch.classList.toggle('open');if(row)row.classList.toggle('open');
}
