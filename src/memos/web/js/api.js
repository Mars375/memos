// ── api.js — API calls: refreshGraph, addMemory, forgetSelected, buildKGEdges, fetchEntityExtra ──

// Build KG edges: map KG entity names to node IDs by matching content/tags
function buildKGEdges(nodes, kgFacts){
  // Build a lookup: entity name (lowercase) -> node id
  const entityToNode={};
  nodes.forEach(n=>{
    (n.tags||[]).forEach(t=>{ entityToNode[t.toLowerCase()]=entityToNode[t.toLowerCase()]||n.id; });
    // Try first word / phrase from content
    const words=(n.content||'').match(/\b[A-Z][a-z]{2,}\b/g)||[];
    words.forEach(w=>{ entityToNode[w.toLowerCase()]=entityToNode[w.toLowerCase()]||n.id; });
  });
  const edges=[];const seen=new Set();
  kgFacts.forEach(f=>{
    const s=entityToNode[(f.subject||'').toLowerCase()];
    const t=entityToNode[(f.object||'').toLowerCase()];
    if(s&&t&&s!==t){
      const key=[s,t].sort().join('|');
      if(!seen.has(key)){seen.add(key);edges.push({source:s,target:t,predicate:f.predicate,type:'kg'});}
    }
  });
  return edges;
}

async function refreshGraph(){
  document.getElementById('loading').style.display='flex';
  try{
    const [gd,st,an,kgr]=await Promise.all([
      fetch(API+'/graph').then(r=>r.json()),
      fetch(API+'/stats').then(r=>r.json()),
      fetch(API+'/analytics/summary?days=14').then(r=>r.json()).catch(()=>null),
      fetch(API+'/kg/labels').then(r=>r.json()).catch(()=>null),
    ]);
    GD.nodes=gd.nodes;GD.edges=gd.edges;
    // Build KG edges from active KG facts
    const allFacts=[];
    if(kgr&&kgr.label_stats){
      try{
        const [ex,inf,amb]=await Promise.all([
          fetch(API+'/kg/labels?label=EXTRACTED').then(r=>r.json()).catch(()=>({facts:[]})),
          fetch(API+'/kg/labels?label=INFERRED').then(r=>r.json()).catch(()=>({facts:[]})),
          fetch(API+'/kg/labels?label=AMBIGUOUS').then(r=>r.json()).catch(()=>({facts:[]})),
        ]);
        allFacts.push(...(ex.facts||[]),...(inf.facts||[]),...(amb.facts||[]));
      }catch(_){}
    }
    GD.kgEdges=buildKGEdges(gd.nodes,allFacts);

    const totalLinks=gd.meta.total_edges+GD.kgEdges.length;
    document.getElementById('s-nodes').textContent=gd.meta.total_nodes;
    document.getElementById('s-tags').textContent=gd.meta.total_tags;
    document.getElementById('s-edges').textContent=totalLinks;
    document.getElementById('s-decay').textContent=st.decay_candidates??0;
    renderAnalytics(an);
    buildTagTree();
    await buildNSTree();
    await loadKGLabels();
    buildNSChips();
    detectClusters(); // P1: detect connected components
    computeTimeRange(); // P2: compute min/max timestamps
    updateHealthPanel(); // P2: health dashboard
    initGraph();
  }finally{
    document.getElementById('loading').style.display='none';
  }
}

async function addMemory(){
  const content=document.getElementById('new-content').value.trim();
  if(!content)return;
  const tags=document.getElementById('new-tags').value.split(',').map(t=>t.trim()).filter(Boolean);
  const ns=document.getElementById('new-ns').value.trim()||'default';
  await fetch(API+'/learn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,tags,namespace:ns,importance:.5})});
  document.getElementById('new-content').value='';document.getElementById('new-tags').value='';document.getElementById('new-ns').value='';
  closeAddModal();refreshGraph();
}

async function forgetSelected(){
  if(!selId)return;
  await fetch(API+'/memory/'+selId,{method:'DELETE'});
  selId=null;closeRightPanel();refreshGraph();
}

async function fetchEntityExtra(entity){
  const extra=document.getElementById('entity-extra');
  if(!extra)return;
  extra.textContent='Loading entity: '+entity+'\u2026';
  try{
    const detail=await fetch(API+'/brain/entity/'+encodeURIComponent(entity)).then(r=>r.json());
    if(detail.status!=='ok'){extra.textContent='';return;}
    extra.textContent='';
    const h=document.createElement('div');h.className='entity-block';
    const htitle=document.createElement('h3');htitle.textContent='Entity: '+entity;
    h.appendChild(htitle);extra.appendChild(h);

    if((detail.kg_facts||[]).length){
      const block=document.createElement('div');block.className='entity-block';
      const t=document.createElement('h3');t.textContent='KG facts';block.appendChild(t);
      detail.kg_facts.forEach(f=>{
        const row=document.createElement('div');row.className='entity-fact';
        const subj=document.createElement('strong');subj.textContent=f.subject||'';
        const pred=document.createElement('span');
        pred.style.cssText='color:var(--text2);font-style:italic';
        pred.textContent=' \u2013'+(f.predicate||'')+'\u2192 ';
        const obj=document.createElement('strong');obj.textContent=f.object||'';
        const meta=document.createElement('div');
        meta.className='entity-meta';meta.textContent=f.confidence_label||'EXTRACTED';
        row.appendChild(subj);row.appendChild(pred);row.appendChild(obj);row.appendChild(meta);
        block.appendChild(row);
      });
      extra.appendChild(block);
    }

    if((detail.kg_neighbors||[]).length){
      const block=document.createElement('div');block.className='entity-block';
      const t=document.createElement('h3');t.textContent='Graph neighbors';block.appendChild(t);
      detail.kg_neighbors.forEach(n=>{
        const btn=document.createElement('button');
        btn.className='entity-link';
        btn.textContent=n.entity+' ('+( n.relation_count||0)+')';
        btn.onclick=()=>openEntityPanel(n.entity);
        block.appendChild(btn);
      });
      extra.appendChild(block);
    }
  }catch(_){extra.textContent='';}
}

refreshGraph();
setInterval(refreshGraph,60000);
