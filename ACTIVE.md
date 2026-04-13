# ACTIVE.md — Chantier MemOS

## Statut : ✅ Phase 1 Maintenance COMPLÈTE — en route vers Phase 2 Dashboard P1

**Dernière session** : 2026-04-13 — Dashboard modularisation (#40) + image Docker all-in-one
**Base** : `main` v2.2.0 — branche `main` (stable)
**Validation** : `pytest -q` → **1534 passed**

## Dernière action

### Corrections de bugs (avril 2026)
- **#31** — Noms de speakers Unicode corrigés (regex étendue aux caractères non-ASCII)
- **#32** — Endpoint `mine/conversation` accepte désormais `text` ET `content` comme champs d'entrée
- **#35** — Utilisation de `host.docker.internal` à la place de l'IP bridge Docker fixe

### Dashboard — Canvas force-graph (#36)
- Remplacement du SVG D3 par un Canvas force-graph (bibliothèque `force-graph`)
- P1 : clustering, filtre de profondeur, tooltip survol, modes de couleur
- P2 : slider time-lapse, panneau santé, correction visibilité des liens

### Dashboard — Modularisation (#40)
- Refactorisation du dashboard monolithique en modules distincts (fix #40)
- Tests et lint corrigés suite à la modularisation
- P2/P3 complétés : issue #39 clôturée (feat(dashboard))

### Docker all-in-one
- Image Docker tout-en-un : `ghcr.io/mars375/memos:latest`
- Profil `memos-standalone` dans `docker-compose.yml` — démarrage zéro-dépendance
- Déploiement : `docker compose up memos-standalone`

### Planning initialisé
- Répertoire `.planning/` créé le 13 avril 2026 (cartographie codebase + feuille de route)

## DONE — Phase 1 Maintenance (13 avril 2026)
- **MAINT-01** ✅ — Version synchro : `pyproject.toml` + `__init__.py` = `2.2.0`
- **MAINT-02** ✅ — Images Docker épinglées : `chromadb/chroma:1.5.7`, `qdrant/qdrant:v1.17.1`
- **MAINT-03** ✅ — Log limits JSON sur les 5 services (`max-size: 10m, max-file: 3`)
- **MAINT-04** ✅ — CI matrix étendue à Python 3.11 / 3.12 / 3.13
- **MAINT-05** ✅ — `ACTIVE.md` mis à jour (v2.2.0, 1534 tests, canvas force-graph, all-in-one Docker)
- **MAINT-06** ✅ — `src/memos/miner/` supprimé (413 lignes orphelines, zéro import cassé)

## IN PROGRESS / IN REVIEW
- **Phase 2 — Dashboard P1** [NEXT] — community detection, depth filter, hover preview enrichi

## Prochaine étape
- **Phase 2 — Dashboard P1** : `/gsd:plan-phase 2`
  - Community detection + nœuds colorés par cluster (Leiden / connected components)
  - Depth filter / local graph (slider 1-5 hops)
  - Hover preview riche (content, tags, namespace, degree)
