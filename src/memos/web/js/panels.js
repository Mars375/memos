// ── panels.js — Memory detail, entity panel, tooltip ──

// ── P1: Hover tooltip ───────────────────────────────────────────
function createTooltip(){
  if(tooltipEl)return tooltipEl;
  tooltipEl=document.createElement('div');
  tooltipEl.id='graph-tooltip';
  tooltipEl.style.cssText='position:fixed;z-index:10000;pointer-events:none;display:none;'+
    'background:rgba(16,16,31,0.95);border:1px solid rgba(167,139,250,0.3);border-radius:8px;'+
    'padding:10px 14px;max-width:300px;font-size:13px;color:#d2daff;'+
    'box-shadow:0 4px 20px rgba(0,0,0,0.5);line-height:1.5;';
  document.body.appendChild(tooltipEl);
  return tooltipEl;
}
function showTooltip(node,x,y){
  const tt=createTooltip();
  const deg=degreeMap[node.id]||0;
  const imp=(node.importance||0).toFixed(2);
  const age=node.age_days!==undefined?node.age_days.toFixed(0)+'d':'?';
  const ns=node.namespace||'default';
  const tags=(node.tags||[]).map(t=>'#'+t).join(' ');
  const snippet=escHtml((node.content||'').slice(0,120));
  tt.innerHTML='<div style="color:#a78bfa;font-weight:600;margin-bottom:4px;">'+escHtml((node.content||'').slice(0,40))+'</div>'+
    '<div style="font-size:11px;color:#8b95b0;">'+escHtml(ns)+' · '+deg+' links · '+imp+' · '+age+'</div>'+
    (tags?'<div style="margin-top:4px;font-size:11px;color:#6ee7b7;">'+tags+'</div>':'')+
    (snippet.length>40?'<div style="margin-top:6px;font-size:12px;color:#9ca3af;">'+snippet+'…</div>':'');
  tt.style.display='block';
  const px=Math.min(x+15, window.innerWidth-320);
  const py=Math.min(y+15, window.innerHeight-160);
  tt.style.left=px+'px';
  tt.style.top=py+'px';
}
function hideTooltip(){
  if(tooltipEl)tooltipEl.style.display='none';
}

function showMemoryDetail(d){
  const rp=document.getElementById('right-panel');
  const title=document.getElementById('rp-title');
  const subtitle=document.getElementById('rp-subtitle');
  const body=document.getElementById('rp-body');

  title.textContent=(d.content||'').slice(0,45)||d.id.slice(0,8)+'...';
  subtitle.textContent='Memory \u00b7 '+(d.namespace||'default');

  body.textContent='';

  // Content block
  const contentDiv=document.createElement('div');
  contentDiv.className='dc-content';
  contentDiv.textContent=d.content||'';
  body.appendChild(contentDiv);

  // Tags
  const tagsDiv=document.createElement('div');
  tagsDiv.style.marginBottom='10px';
  if(d.tags&&d.tags.length){
    d.tags.forEach(t=>{
      const sp=document.createElement('span');
      sp.className='badge';
      sp.style.background=tc(t)+'22';
      sp.style.color=tc(t);
      sp.style.border='1px solid '+tc(t)+'44';
      sp.textContent='#'+t;
      tagsDiv.appendChild(sp);
    });
  } else {
    const empty=document.createElement('span');
    empty.style.cssText='color:var(--text2);font-size:.8em';
    empty.textContent='No tags';
    tagsDiv.appendChild(empty);
  }
  body.appendChild(tagsDiv);

  // Meta grid
  const metaDiv=document.createElement('div');
  metaDiv.className='dc-meta';
  [['Importance',(d.importance*100).toFixed(0)+'%'],['Age',(d.age_days||0)+'d'],
   ['Accessed',(d.access_count||0)+'\u00d7'],['ID',d.id.slice(0,8)+'...']].forEach(([l,v])=>{
    const sp=document.createElement('span');
    const strong=document.createElement('strong');
    strong.textContent=l;
    sp.appendChild(strong);
    sp.appendChild(document.createTextNode(v));
    metaDiv.appendChild(sp);
  });
  body.appendChild(metaDiv);

  // Forget button
  const forgetBtn=document.createElement('button');
  forgetBtn.className='btn btn-danger';
  forgetBtn.textContent='\uD83D\uDDD1 Forget';
  forgetBtn.onclick=forgetSelected;
  body.appendChild(forgetBtn);

  // Entity extra placeholder
  const extra=document.createElement('div');
  extra.id='entity-extra';
  extra.style.marginTop='16px';
  body.appendChild(extra);

  rp.classList.add('open');
}

function extractEntitiesFromNode(d){
  const seen=new Set();const out=[];
  const add=v=>{const s=(v||'').trim();if(!s||s.length<3)return;const k=s.toLowerCase();if(!seen.has(k)){seen.add(k);out.push(s);}};
  (d.tags||[]).filter(t=>/[A-Z]/.test(t)).forEach(add);
  ((d.content||'').match(/\b(?:[A-Z][\w-]*(?:\s+[A-Z][\w-]*)+|[A-Z][a-z]{3,})\b/g)||[]).forEach(add);
  return out.slice(0,5);
}

async function openEntityPanel(entity){
  const rp=document.getElementById('right-panel');
  document.getElementById('rp-title').textContent=entity;
  document.getElementById('rp-subtitle').textContent='Entity detail \u00b7 KG + Wiki';
  const body=document.getElementById('rp-body');
  body.textContent='Loading entity detail\u2026';
  rp.classList.add('open');
  try{
    const [detail,subgraph]=await Promise.all([
      fetch(API+'/brain/entity/'+encodeURIComponent(entity)).then(r=>r.json()),
      fetch(API+'/brain/entity/'+encodeURIComponent(entity)+'/subgraph?depth=2').then(r=>r.json()).catch(()=>null),
    ]);
    if(detail.status!=='ok'){body.textContent='Failed to load.';return;}
    body.textContent='';

    const sections=[
      {title:'Community',content:detail.community||'n/a',type:'text'},
      {title:'Wiki page',content:detail.wiki_page,type:'pre'},
      {title:'Top memories',items:detail.memories,type:'memories'},
      {title:'KG facts',items:detail.kg_facts,type:'facts'},
      {title:'Graph neighbors',items:detail.kg_neighbors,type:'neighbors'},
      {title:'Backlinks',items:detail.backlinks,type:'backlinks'},
      {title:'Subgraph',content:(subgraph&&subgraph.status==='ok')?subgraph.nodes.length+' nodes \u00b7 '+subgraph.edges.length+' edges':'Unavailable',type:'text'},
    ];
    sections.forEach(sec=>{
      if(sec.type==='text'||(sec.type==='pre'&&sec.content)){
        const block=document.createElement('div');block.className='entity-block';
        const h=document.createElement('h3');h.textContent=sec.title;block.appendChild(h);
        if(sec.type==='pre'){const pre=document.createElement('div');pre.className='entity-pre';pre.textContent=sec.content;block.appendChild(pre);}
        else{const p=document.createElement('div');p.textContent=sec.content;block.appendChild(p);}
        body.appendChild(block);
      } else if(sec.items&&sec.items.length){
        const block=document.createElement('div');block.className='entity-block';
        const h=document.createElement('h3');h.textContent=sec.title;block.appendChild(h);
        sec.items.forEach(item=>{
          if(sec.type==='memories'){
            const div=document.createElement('div');div.className='entity-memory';
            const t=document.createElement('div');t.textContent=item.content||'';div.appendChild(t);
            const m=document.createElement('div');m.className='entity-meta';
            m.textContent='importance '+Number(item.importance||0).toFixed(2)+' \u00b7 '+(item.source||'memory');
            div.appendChild(m);block.appendChild(div);
          } else if(sec.type==='facts'){
            const div=document.createElement('div');div.className='entity-fact';
            const subj=document.createElement('strong');subj.textContent=item.subject||'';
            const pred=document.createElement('span');pred.style.cssText='color:var(--text2);font-style:italic';
            pred.textContent=' \u2013'+(item.predicate||'')+'\u2192 ';
            const obj=document.createElement('strong');obj.textContent=item.object||'';
            const meta=document.createElement('div');meta.className='entity-meta';
            meta.textContent=item.confidence_label||'EXTRACTED';
            div.appendChild(subj);div.appendChild(pred);div.appendChild(obj);div.appendChild(meta);
            block.appendChild(div);
          } else if(sec.type==='neighbors'){
            const btn=document.createElement('button');btn.className='entity-link';
            btn.textContent=item.entity+' ('+(item.relation_count||0)+')';
            btn.onclick=()=>openEntityPanel(item.entity);block.appendChild(btn);
          } else if(sec.type==='backlinks'){
            const btn=document.createElement('button');btn.className='entity-link';
            btn.textContent=item;
            btn.onclick=()=>openEntityPanel(item);block.appendChild(btn);
          }
        });
        body.appendChild(block);
      }
    });
  }catch(_){body.textContent='Error loading entity.';}
}

function closeRightPanel(){document.getElementById('right-panel').classList.remove('open');}
