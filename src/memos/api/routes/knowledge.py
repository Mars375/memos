"""Knowledge Graph, Brain Search, Palace, Context, and Graph routes."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter


def create_knowledge_router(memos, _kg, _palace, _context_stack) -> APIRouter:
    """Create the knowledge-related API router."""
    router = APIRouter()

    # ── Knowledge Graph ───────────────────────────────────────

    @router.post("/api/v1/kg/facts")
    async def kg_add_fact(body: dict):
        """Add a triple to the temporal knowledge graph."""
        subject = body.get("subject", "").strip()
        predicate = body.get("predicate", "").strip()
        obj = body.get("object", "").strip()
        if not subject or not predicate or not obj:
            return {"status": "error", "message": "subject, predicate and object are required"}
        try:
            from ...knowledge_graph import KnowledgeGraph

            confidence_label = body.get("confidence_label", "EXTRACTED")
            if confidence_label not in KnowledgeGraph.VALID_LABELS:
                return {
                    "status": "error",
                    "message": f"Invalid confidence_label. Must be one of {KnowledgeGraph.VALID_LABELS}",
                }
            fact_id = _kg.add_fact(
                subject=subject,
                predicate=predicate,
                object=obj,
                valid_from=body.get("valid_from"),
                valid_to=body.get("valid_to"),
                confidence=float(body.get("confidence", 1.0)),
                confidence_label=confidence_label,
                source=body.get("source"),
            )
            return {"status": "ok", "id": fact_id, "confidence_label": confidence_label}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/kg/query")
    async def kg_query(entity: str, time: Optional[str] = None, direction: str = "both"):
        try:
            facts = _kg.query(entity, time=time, direction=direction)
            return {"status": "ok", "entity": entity, "facts": facts}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/kg/timeline")
    async def kg_timeline(entity: str):
        try:
            facts = _kg.timeline(entity)
            return {"status": "ok", "entity": entity, "timeline": facts}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.delete("/api/v1/kg/facts/{fact_id}")
    async def kg_invalidate(fact_id: str):
        ok = _kg.invalidate(fact_id)
        return {"status": "ok" if ok else "not_found"}

    @router.get("/api/v1/kg/stats")
    async def kg_stats():
        return _kg.stats()

    @router.get("/api/v1/kg/labels")
    async def kg_labels(label: Optional[str] = None, active_only: bool = True):
        from ...knowledge_graph import KnowledgeGraph

        if label:
            if label not in KnowledgeGraph.VALID_LABELS:
                return {"status": "error", "message": f"Invalid label. Must be one of {KnowledgeGraph.VALID_LABELS}"}
            facts = _kg.query_by_label(label, active_only=active_only)
            return {"status": "ok", "label": label, "facts": facts, "count": len(facts)}
        return {"status": "ok", "label_stats": _kg.label_stats()}

    @router.post("/api/v1/kg/infer")
    async def kg_infer(body: dict):
        predicate = body.get("predicate", "").strip()
        if not predicate:
            return {"status": "error", "message": "predicate is required"}
        try:
            new_ids = _kg.infer_transitive(
                predicate=predicate,
                inferred_predicate=body.get("inferred_predicate"),
                max_depth=int(body.get("max_depth", 3)),
            )
            return {"status": "ok", "inferred_count": len(new_ids), "fact_ids": new_ids}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/kg/paths")
    async def kg_paths(entity_a: str, entity_b: str, max_hops: int = 3, max_paths: int = 10):
        paths = _kg.find_paths(entity_a, entity_b, max_hops=max_hops, max_paths=max_paths)
        return {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "max_hops": max_hops,
            "paths": [
                {
                    "hops": len(p),
                    "edges": [
                        {
                            "id": t["id"],
                            "subject": t["subject"],
                            "predicate": t["predicate"],
                            "object": t["object"],
                            "confidence": t["confidence"],
                        }
                        for t in p
                    ],
                }
                for p in paths
            ],
            "total": len(paths),
        }

    @router.get("/api/v1/kg/neighbors")
    async def kg_neighbors(entity: str, depth: int = 1, direction: str = "both"):
        result = _kg.neighbors(entity, depth=depth, direction=direction)
        return {
            "center": result["center"],
            "depth": result["depth"],
            "total_nodes": len(result["nodes"]),
            "total_edges": len(result["edges"]),
            "nodes": result["nodes"],
            "layers": result["layers"],
            "edges": [
                {
                    "id": t["id"],
                    "subject": t["subject"],
                    "predicate": t["predicate"],
                    "object": t["object"],
                    "confidence": t["confidence"],
                }
                for t in result["edges"]
            ],
        }

    @router.get("/api/v1/kg/communities")
    async def kg_communities(algorithm: str = "label_propagation"):
        """Detect entity communities using label-propagation clustering."""
        try:
            communities = _kg.detect_communities(algorithm=algorithm)
            return {"status": "ok", "communities": communities, "total": len(communities)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/kg/god-nodes")
    async def kg_god_nodes(top_k: int = 10):
        """Return the highest-degree entities in the knowledge graph."""
        try:
            nodes = _kg.god_nodes(top_k=top_k)
            return {"status": "ok", "nodes": nodes, "total": len(nodes)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/kg/surprising")
    async def kg_surprising(top_k: int = 10):
        """Find edges connecting entities from different communities."""
        try:
            connections = _kg.surprising_connections(top_k=top_k)
            return {"status": "ok", "connections": connections, "total": len(connections)}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Brain Search ──────────────────────────────────────────

    @router.post("/api/v1/brain/search")
    async def brain_search(body: dict):
        """Unified search across memories, living wiki pages, and the knowledge graph."""
        from ...brain import BrainSearch

        query = body.get("query", "").strip()
        if not query:
            return {"status": "error", "message": "query is required"}
        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=body.get("wiki_dir"))
            result = searcher.search(
                query,
                top_k=int(body.get("top_k", 10)),
                filter_tags=body.get("tags"),
                min_score=float(body.get("min_score", 0.0)),
                retrieval_mode=body.get("retrieval_mode", "hybrid"),
                max_context_chars=int(body.get("max_context_chars", 2000)),
                auto_file=bool(body.get("auto_file", False)),
            )
            payload = result.to_dict()
            payload["status"] = "ok"
            return payload
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/brain/entity/{name}")
    async def brain_entity_detail(
        name: str, top_memories: int = 5, neighbor_limit: int = 12, wiki_dir: str | None = None
    ):
        """Return a unified entity detail view across wiki, memories, and KG."""
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            detail = searcher.entity_detail(name, top_memories=top_memories, neighbor_limit=neighbor_limit)
            payload = detail.to_dict()
            payload["status"] = "ok"
            return payload
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/brain/entity/{name}/subgraph")
    async def brain_entity_subgraph(name: str, depth: int = 2, wiki_dir: str | None = None):
        """Return an ego-network subgraph for an entity."""
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            subgraph = searcher.entity_subgraph(name, depth=depth)
            return {
                "status": "ok",
                "entity": subgraph.center,
                "depth": subgraph.depth,
                "nodes": subgraph.nodes,
                "edges": subgraph.edges,
                "layers": subgraph.layers,
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/brain/connections")
    async def brain_surprising_connections(top: int = 5, wiki_dir: str | None = None):
        """Find surprising cross-domain connections between communities."""
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            connections = searcher.surprising_connections(top_n=top)
            return {
                "status": "ok",
                "connections": connections,
                "total": len(connections),
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/brain/suggest")
    async def brain_suggest(top_k: int = 5, wiki_dir: str | None = None):
        """Suggest exploration questions based on the knowledge graph structure."""
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            suggestions = searcher.suggest_questions(top_k=top_k)
            return {
                "status": "ok",
                "suggestions": [
                    {
                        "question": sq.question,
                        "category": sq.category,
                        "score": sq.score,
                        "entities": sq.entities,
                    }
                    for sq in suggestions
                ],
                "total": len(suggestions),
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/brain/suggestions")
    async def brain_suggestions(n: int = 5, wiki_dir: str | None = None):
        """Suggest exploration questions based on KG gaps and unexplored areas.

        Generates questions from god nodes, small communities, ambiguous facts,
        and wiki entities with few facts. Returns natural-language strings.
        """
        from ...brain import BrainSearch

        try:
            searcher = BrainSearch(memos, kg=_kg, wiki_dir=wiki_dir)
            suggestions = searcher.suggest_questions(top_k=n)
            return {
                "status": "ok",
                "questions": [sq.question for sq in suggestions],
                "details": [
                    {
                        "question": sq.question,
                        "category": sq.category,
                        "score": sq.score,
                        "entities": sq.entities,
                    }
                    for sq in suggestions
                ],
                "total": len(suggestions),
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Palace ────────────────────────────────────────────────

    @router.get("/api/v1/palace/wings")
    async def palace_list_wings():
        return {"status": "ok", "wings": _palace.list_wings()}

    @router.post("/api/v1/palace/wings")
    async def palace_create_wing(body: dict):
        name = body.get("name", "").strip()
        if not name:
            return {"status": "error", "message": "name is required"}
        try:
            wing_id = _palace.create_wing(name, description=body.get("description", ""))
            return {"status": "ok", "id": wing_id, "name": name}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/palace/rooms")
    async def palace_list_rooms(wing: Optional[str] = None):
        try:
            return {"status": "ok", "rooms": _palace.list_rooms(wing_name=wing)}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @router.post("/api/v1/palace/rooms")
    async def palace_create_room(body: dict):
        wing_name, room_name = body.get("wing", "").strip(), body.get("name", "").strip()
        if not wing_name or not room_name:
            return {"status": "error", "message": "wing and name are required"}
        try:
            room_id = _palace.create_room(wing_name, room_name, description=body.get("description", ""))
            return {"status": "ok", "id": room_id, "wing": wing_name, "name": room_name}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @router.post("/api/v1/palace/assign")
    async def palace_assign(body: dict):
        memory_id, wing_name = body.get("memory_id", "").strip(), body.get("wing", "").strip()
        if not memory_id or not wing_name:
            return {"status": "error", "message": "memory_id and wing are required"}
        try:
            _palace.assign(memory_id, wing_name, room_name=body.get("room"))
            return {"status": "ok", "memory_id": memory_id, "wing": wing_name, "room": body.get("room")}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    @router.delete("/api/v1/palace/assign/{memory_id}")
    async def palace_unassign(memory_id: str):
        _palace.unassign(memory_id)
        return {"status": "ok", "memory_id": memory_id}

    @router.get("/api/v1/palace/recall")
    async def palace_recall_endpoint(query: Optional[str] = None, wing: Optional[str] = None, room: Optional[str] = None, top: int = 10):
        from ...palace import PalaceRecall as _PalaceRecall

        # When wing+room are provided, query is optional (use '*' as catch-all)
        effective_query = query if query else "*"
        pr = _PalaceRecall(_palace)
        results = pr.palace_recall(memos, effective_query, wing_name=wing, room_name=room, top=top)
        return {
            "status": "ok",
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
        }

    @router.get("/api/v1/palace/stats")
    async def palace_stats_endpoint():
        return {"status": "ok", **_palace.stats()}

    @router.post("/api/v1/palace/diary")
    async def palace_write_diary(body: dict):
        """Write a diary entry for an agent."""
        agent = body.get("agent_name", body.get("agent", "")).strip()
        content = body.get("entry", body.get("content", "")).strip()
        tags = body.get("tags")
        if not agent or not content:
            return {"status": "error", "message": "agent_name and entry are required"}
        try:
            entry_id = _palace.append_diary(agent, content, tags=tags)
            return {"status": "ok", "id": entry_id, "agent_name": agent}
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/palace/diary/{agent}")
    async def palace_read_diary(agent: str, limit: int = 20):
        """Read diary entries for an agent, newest first."""
        try:
            entries = _palace.read_diary(agent, limit=limit)
            return {"status": "ok", "agent_name": agent, "entries": entries, "count": len(entries)}
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

    @router.post("/api/v1/palace/agents")
    async def palace_provision_agent(body: dict):
        """Auto-provision an agent wing with default rooms (diary, context, learnings)."""
        name = body.get("name", "").strip()
        if not name:
            return {"status": "error", "message": "name is required"}
        try:
            wing = _palace.ensure_agent_wing(name, description=body.get("description", ""))
            return {"status": "ok", "wing": wing}
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

    @router.get("/api/v1/palace/agents")
    async def palace_list_agents():
        """Discover all agents with agent- wings in the palace."""
        agents = _palace.list_agents()
        return {"status": "ok", "agents": agents, "total": len(agents)}

    # ── Context Stack ─────────────────────────────────────────

    @router.get("/api/v1/context/wake-up")
    async def context_wake_up(max_chars: int = 2000, l1_top: int = 15, include_stats: bool = True):
        output = _context_stack.wake_up(max_chars=max_chars, l1_top=l1_top, include_stats=include_stats)
        return {"status": "ok", "context": output, "chars": len(output)}

    @router.get("/api/v1/context/identity")
    async def context_get_identity():
        content = _context_stack.get_identity()
        return {"status": "ok", "identity": content, "exists": bool(content)}

    @router.post("/api/v1/context/identity")
    async def context_set_identity(body: dict):
        content = body.get("content")
        if content is None:
            return {"status": "error", "message": "content is required"}
        _context_stack.set_identity(content)
        return {"status": "ok", "chars": len(content)}

    @router.get("/api/v1/context/for")
    async def context_for_query(query: str, max_chars: int = 1500, top: int = 10):
        output = _context_stack.context_for(query=query, max_chars=max_chars, top=top)
        return {"status": "ok", "context": output, "query": query, "chars": len(output)}

    # ── Memory Graph ──────────────────────────────────────────

    @router.get("/api/v1/graph")
    async def api_graph(min_shared_tags: int = 1, limit: int = 500, created_before: Optional[float] = None):
        """Return memory graph: nodes + edges based on shared tags.

        created_before: optional Unix timestamp — only include memories created before this time.
        """
        items = memos._store.list_all(namespace=memos._namespace)
        now = time.time()
        nodes = []
        for item in items[:limit]:
            if item.is_expired:
                continue
            if created_before is not None and item.created_at > created_before:
                continue
            age_days = (now - item.created_at) / 86400
            nodes.append(
                {
                    "id": item.id,
                    "label": item.content[:60] + ("…" if len(item.content) > 60 else ""),
                    "content": item.content,
                    "tags": item.tags,
                    "importance": item.importance,
                    "relevance": item.relevance_score,
                    "age_days": round(age_days, 1),
                    "access_count": item.access_count,
                    "primary_tag": item.tags[0] if item.tags else "__untagged__",
                    "namespace": getattr(item, "namespace", memos._namespace or "default"),
                    "created_at": item.created_at,
                }
            )
        edges = []
        tag_to_ids: dict[str, list[str]] = {}
        for n in nodes:
            for tag in n["tags"]:
                tag_to_ids.setdefault(tag, []).append(n["id"])
        seen = set()
        for tag, ids in tag_to_ids.items():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    key = tuple(sorted([ids[i], ids[j]]))
                    if key not in seen:
                        seen.add(key)
                        edges.append({"source": ids[i], "target": ids[j], "shared_tags": [tag], "weight": 1})
                    else:
                        for e in edges:
                            if e["source"] == key[0] and e["target"] == key[1]:
                                e["weight"] += 1
                                e["shared_tags"].append(tag)
                                break
        if min_shared_tags > 1:
            edges = [e for e in edges if e["weight"] >= min_shared_tags]
        stats = memos.stats()
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_memories": stats.total_memories,
                "total_tags": stats.total_tags,
                "created_before": created_before,
            },
        }

    # ── Living Wiki ────────────────────────────────────────────────

    @router.get("/api/v1/wiki/pages")
    async def wiki_list_pages():
        """List all living wiki pages (name, slug, memory_count, updated_at)."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            pages = wiki.list_pages()
            return {
                "status": "ok",
                "pages": [
                    {
                        "name": p.entity,
                        "slug": p.slug,
                        "memory_count": p.memory_count,
                        "updated_at": p.updated_at,
                    }
                    for p in pages
                ],
                "total": len(pages),
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "pages": [], "total": 0}

    @router.post("/api/v1/wiki/pages")
    async def wiki_create_page(body: dict):
        """Create a new living wiki page.

        Request body:
            entity (str): Name of the entity / page.
            entity_type (str, optional): One of person, project, concept, topic, resource, contact, default.
            content (str, optional): Initial body content appended after template.
        """
        entity = body.get("entity", "").strip()
        if not entity:
            return {"status": "error", "error": "'entity' is required"}
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            result = wiki.create_page(
                entity=entity,
                entity_type=body.get("entity_type", "default"),
                content=body.get("content", ""),
            )
            return {**result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/api/v1/wiki/page/{slug}")
    async def wiki_read_page(slug: str):
        """Read a single living wiki page by slug or entity name."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            # Try slug first, then as entity name directly
            content = wiki.read_page(slug)
            if content is None:
                # Try with spaces instead of hyphens
                content = wiki.read_page(slug.replace("-", " "))
            return {
                "status": "ok" if content is not None else "not_found",
                "slug": slug,
                "content": content or "",
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "content": ""}

    @router.get("/api/v1/wiki/search")
    async def wiki_search_pages(q: str):
        """Search living wiki pages."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            results = wiki.search(q)
            return {"status": "ok", "results": results, "query": q}
        except Exception as e:
            return {"status": "error", "error": str(e), "results": []}

    @router.get("/api/v1/wiki/index")
    async def wiki_get_index():
        """Return the auto-generated wiki index (index.md content)."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            content = wiki.generate_index()
            return {"status": "ok", "content": content}
        except Exception as e:
            return {"status": "error", "error": str(e), "content": ""}

    @router.post("/api/v1/wiki/regenerate-index")
    async def wiki_regenerate_index():
        """Regenerate the Karpathy-style wiki index.md and return its content."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            content = wiki.regenerate_index()
            return {"status": "ok", "content": content}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/api/v1/wiki/log")
    async def wiki_get_log():
        """Return the wiki activity log (log.md content)."""
        try:
            from ...wiki_living import LivingWikiEngine

            wiki = LivingWikiEngine(memos)
            content = wiki.get_log_markdown()
            return {"status": "ok", "content": content}
        except Exception as e:
            return {"status": "error", "error": str(e), "content": ""}

    return router
