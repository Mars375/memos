"""Knowledge graph API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ..errors import handle_exception, not_found, validation_error
from ..schemas import FactRequest, InferRequest


def create_kg_router(_kg) -> APIRouter:
    """Create knowledge-graph routes."""
    router = APIRouter()

    @router.post("/api/v1/kg/facts")
    async def kg_add_fact(body: FactRequest):
        try:
            from ...knowledge_graph import KnowledgeGraph

            confidence_label = body.confidence_label
            if confidence_label not in KnowledgeGraph.VALID_LABELS:
                return validation_error(f"Invalid confidence_label. Must be one of {KnowledgeGraph.VALID_LABELS}")
            fact_id = _kg.add_fact(
                subject=body.subject,
                predicate=body.predicate,
                object=body.object,
                valid_from=body.valid_from,
                valid_to=body.valid_to,
                confidence=body.confidence,
                confidence_label=confidence_label,
                source=body.source,
            )
            return {"status": "ok", "id": fact_id, "confidence_label": confidence_label}
        except Exception as exc:
            return handle_exception(exc, context="kg_add_fact")

    @router.get("/api/v1/kg/query")
    async def kg_query(entity: str, time: Optional[str] = None, direction: str = "both"):
        try:
            facts = _kg.query(entity, time=time, direction=direction)
            return {"status": "ok", "entity": entity, "facts": facts}
        except Exception as exc:
            return handle_exception(exc, context="kg_query")

    @router.get("/api/v1/kg/timeline")
    async def kg_timeline(entity: str):
        try:
            facts = _kg.timeline(entity)
            return {"status": "ok", "entity": entity, "timeline": facts}
        except Exception as exc:
            return handle_exception(exc, context="kg_timeline")

    @router.delete("/api/v1/kg/facts/{fact_id}")
    async def kg_invalidate(fact_id: str):
        ok = _kg.invalidate(fact_id)
        if not ok:
            return not_found(f"Fact {fact_id} not found")
        return {"status": "ok", "invalidated": fact_id}

    @router.get("/api/v1/kg/stats")
    async def kg_stats():
        return _kg.stats()

    @router.get("/api/v1/kg/labels")
    async def kg_labels(label: Optional[str] = None, active_only: bool = True):
        from ...knowledge_graph import KnowledgeGraph

        if label:
            if label not in KnowledgeGraph.VALID_LABELS:
                return validation_error(f"Invalid label. Must be one of {KnowledgeGraph.VALID_LABELS}")
            facts = _kg.query_by_label(label, active_only=active_only)
            return {"status": "ok", "label": label, "facts": facts, "count": len(facts)}
        return {"status": "ok", "label_stats": _kg.label_stats()}

    @router.post("/api/v1/kg/infer")
    async def kg_infer(body: InferRequest):
        try:
            new_ids = _kg.infer_transitive(
                predicate=body.predicate,
                inferred_predicate=body.inferred_predicate,
                max_depth=body.max_depth,
            )
            return {"status": "ok", "inferred_count": len(new_ids), "fact_ids": new_ids}
        except Exception as exc:
            return handle_exception(exc, context="kg_infer")

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
        try:
            communities = _kg.detect_communities(algorithm=algorithm)
            return {"status": "ok", "communities": communities, "total": len(communities)}
        except Exception as exc:
            return handle_exception(exc, context="kg_communities")

    @router.get("/api/v1/kg/god-nodes")
    async def kg_god_nodes(top_k: int = 10):
        try:
            nodes = _kg.god_nodes(top_k=top_k)
            return {"status": "ok", "nodes": nodes, "total": len(nodes)}
        except Exception as exc:
            return handle_exception(exc, context="kg_god_nodes")

    @router.get("/api/v1/kg/surprising")
    async def kg_surprising(top_k: int = 10):
        try:
            connections = _kg.surprising_connections(top_k=top_k)
            return {"status": "ok", "connections": connections, "total": len(connections)}
        except Exception as exc:
            return handle_exception(exc, context="kg_surprising")

    return router
