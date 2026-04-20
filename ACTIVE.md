# ACTIVE.md — Chantier MemOS

## Statut : ✅ v2.3.3 stable — hardening follow-up and final split pass integrated

**Dernière session** : 2026-04-20 — merge du gros cleanup structurel + démarrage d’un nouveau pass A/B/C
**Base** : `main` v2.3.3 — branche `main` (stable)
**Validation** : `pytest --collect-only -q` → **2406 tests collectés**

## Derniers chantiers terminés

### Refactor structurel ✅
- Split de `wiki_living.py` en `wiki_engine.py`, `wiki_entities.py`, `wiki_models.py`, `wiki_templates.py`
- Split de `mcp_server.py` vers `mcp_tools/` + registre de tools
- Extraction de facades depuis `core.py`
- Split de `cli/_parser.py` en package `cli/_parser/`
- Split de `cli/commands_memory.py` en modules par responsabilité

### Stabilisation CI ✅
- Nettoyage du formatage `ruff`
- Suppression/alignement des tests Docker obsolètes liés à `docker-compose.yml`
- PR mergée sur `main`

## Backlog actif

### Option A — Foundation (en cours)
- Mise à jour de la documentation projet (`AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `ACTIVE.md`)
- Ajout de tests directs pour les modules splittés (wiki, MCP tools, facades)
- Nettoyage des duplications / artefacts laissés par les splits

### Option B — Hardening (à venir)
- Auth / WebSocket / CORS / path handling / URL ingest safety
- Réduction du sync-in-async et des principaux hotspots perf

### Option C — Structural follow-up (à venir)
- Split de `src/memos/api/routes/memory.py`
- Split de `src/memos/wiki_engine.py`

## Prochaine étape
- Finaliser Option A avec validation complète (`ruff`, `pytest`)
- Enchaîner sur Option B, puis Option C
