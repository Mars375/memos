# ACTIVE.md — Chantier MemOS

## Statut : ✅ Dashboard modularisé + Docker all-in-one, Phase 1 Maintenance EN COURS

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

## OPEN dans PRIORITIES.md
- **MAINT-01** — Synchroniser version `pyproject.toml` (1.0.0) ↔ `__init__.py` (2.2.0)
- **MAINT-02** — Épingler images Docker tiers à des versions concrètes
- **MAINT-03** — Ajouter log limits JSON au `docker-compose.yml`
- **MAINT-04** — Ajouter Python 3.13 au matrix CI

## IN PROGRESS / IN REVIEW
- **Phase 1 — Maintenance** [EN COURS] — Plans 01-01 à 01-02 (version drift, miner orphelin, etc.)

## Prochaine étape
- **Phase 1 — Maintenance** : compléter les 2 plans restants (01-01, 01-02)
- **Phase 2 — Dashboard P1** : community detection, depth filter, hover preview enrichi
