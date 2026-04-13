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
