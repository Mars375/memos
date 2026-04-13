// ── state.js — Global state variables, constants, config ──

const API='/api/v1';
const PAL=['#7c6ff7','#f97316','#06b6d4','#22c55e','#f43f5e','#a855f7','#eab308','#14b8a6','#ec4899','#64748b','#fb923c','#4ade80','#38bdf8','#c084fc','#fb7185'];

// GD carries both memory edges AND KG edges
let GD={nodes:[],edges:[],kgEdges:[]};
let fg=null; // force-graph instance
let selId=null, sq='';
let activeNS=new Set(), minEdgeWeight=1, minDegree=0;
let highlightNodes=new Set(), highlightLinks=new Set();
let hoverNode=null;
let analyticsChart=null;
const degreeMap={};

// ── P1: Clustering, depth, hover preview, color mode ────────────
let clusterMap={};       // nodeId → clusterId
let clusterColors={};    // clusterId → color
let colorMode='namespace'; // 'namespace' | 'cluster' | 'tag'
let depthLimit=0;        // 0=unlimited, 1-5 = hop limit from selected node
let focusNode=null;      // currently focused node for depth filtering
let tooltipEl=null;      // hover tooltip element
let timeRange=[0,100];   // min/max created_at timestamps
let timePct=100;         // current time slider percentage (0-100)

// ── Layer Memory Stack ──────────────────────────────────────────────
const LAYER_COLORS={0:'#22c55e',1:'#3b82f6',2:'#f97316',3:'#64748b'};
const LAYER_NAMES={0:'L0',1:'L1',2:'L2',3:'L3'};
let layerFilter=null;    // null=all, 0-3=specific layer

function computeLayers(){
  GD.nodes.forEach(n=>{
    if((n.importance||0)>=0.9)n.layer=0;
    else if((n.importance||0)>=0.7||(n.access_count||0)>0)n.layer=1;
    else if((n.age_days||0)>60&&(n.access_count||0)===0)n.layer=3;
    else n.layer=2;
  });
}
