/* ── state.js ── Global shared state ──────────────────────────── */

const API = '/api/v1';

const PAL = ['#7c6ff7','#f97316','#06b6d4','#22c55e','#f43f5e','#a855f7','#eab308','#14b8a6','#ec4899','#64748b','#fb923c','#4ade80','#38bdf8','#c084fc','#fb7185'];
const tcmap = {};
let ci = 0;

// GD carries both memory edges AND KG edges
let GD = { nodes: [], edges: [], kgEdges: [] };
let fg = null; // force-graph instance
let selId = null, sq = '';
let activeNS = new Set(), minEdgeWeight = 1, minDegree = 0;
let highlightNodes = new Set(), highlightLinks = new Set();
let hoverNode = null;
let analyticsChart = null;
const degreeMap = {};
const inDegreeMap = {};
const outDegreeMap = {};
let localGraphMode = false;

// ── P1: Clustering, depth, hover preview, color mode ────────────
let clusterMap = {};       // nodeId → clusterId
let clusterColors = {};    // clusterId → color
let colorMode = 'namespace'; // 'namespace' | 'cluster' | 'tag'
let depthLimit = 0;        // 0=unlimited, 1-5 = hop limit from selected node
let focusNode = null;      // currently focused node for depth filtering
let tooltipEl = null;      // hover tooltip element
let timeRange = [0, 100];  // min/max created_at timestamps
let timePct = 100;         // current time slider percentage (0-100)

const CLUSTER_PALETTE = [
  '#a78bfa', '#34d399', '#f59e0b', '#60a5fa', '#f472b6',
  '#2dd4bf', '#fb923c', '#818cf8', '#4ade80', '#fbbf24',
  '#38bdf8', '#e879f9'
];

// ── Wiki state ─────────────────────────────────────────────────
let wikiPages = [];
let currentWikiPage = null;
let wikiSearchTimeout = null;

// ── Palace state ───────────────────────────────────────────────
let palaceData = { wings: [], rooms: [] };
let activeRoom = null;

// ── Time-travel state ──────────────────────────────────────────
let ttActive = false;

// ── Community detection + god nodes state (Task 5.3) ──────────
let communityMap = {};     // nodeId → communityId (from API)
let communityColors = {};  // communityId → color string
let communityNames = {};   // communityId → label/name
let godNodeIds = new Set(); // set of node IDs that are "god nodes"

const COMMUNITY_PALETTE = [
  '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
  '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabed4',
  '#469990', '#dcbeff', '#9A6324', '#fffac8', '#800000',
  '#aaffc3', '#808000', '#ffd8b1', '#000075', '#a9a9a9'
];
