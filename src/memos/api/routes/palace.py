"""Memory palace API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ..errors import handle_exception, not_found, validation_error
from ..schemas import (
    PalaceAssignRequest,
    PalaceCreateRoomRequest,
    PalaceCreateWingRequest,
    PalaceDiaryWriteRequest,
    PalaceProvisionAgentRequest,
)


def create_palace_router(memos, _palace) -> APIRouter:
    """Create palace routes."""
    router = APIRouter()

    @router.get("/api/v1/palace/wings")
    async def palace_list_wings():
        return {"status": "ok", "wings": _palace.list_wings()}

    @router.post("/api/v1/palace/wings")
    async def palace_create_wing(body: PalaceCreateWingRequest):
        try:
            wing_id = _palace.create_wing(body.name, description=body.description)
            return {"status": "ok", "id": wing_id, "name": body.name}
        except Exception as exc:
            return handle_exception(exc, context="palace_create_wing")

    @router.get("/api/v1/palace/rooms")
    async def palace_list_rooms(wing: Optional[str] = None):
        try:
            return {"status": "ok", "rooms": _palace.list_rooms(wing_name=wing)}
        except KeyError as exc:
            return not_found(str(exc).strip("'"))

    @router.post("/api/v1/palace/rooms")
    async def palace_create_room(body: PalaceCreateRoomRequest):
        try:
            room_id = _palace.create_room(body.wing, body.name, description=body.description)
            return {"status": "ok", "id": room_id, "wing": body.wing, "name": body.name}
        except KeyError as exc:
            return not_found(str(exc).strip("'"))

    @router.post("/api/v1/palace/assign")
    async def palace_assign(body: PalaceAssignRequest):
        try:
            _palace.assign(body.memory_id, body.wing, room_name=body.room)
            return {"status": "ok", "memory_id": body.memory_id, "wing": body.wing, "room": body.room}
        except KeyError as exc:
            return not_found(str(exc).strip("'"))

    @router.delete("/api/v1/palace/assign/{memory_id}")
    async def palace_unassign(memory_id: str):
        _palace.unassign(memory_id)
        return {"status": "ok", "memory_id": memory_id}

    @router.get("/api/v1/palace/recall")
    async def palace_recall_endpoint(
        query: Optional[str] = None, wing: Optional[str] = None, room: Optional[str] = None, top: int = 10
    ):
        from ...palace import PalaceRecall as _PalaceRecall

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
    async def palace_write_diary(body: PalaceDiaryWriteRequest):
        try:
            entry_id = _palace.append_diary(body.agent_name, body.entry, tags=body.tags)
            return {"status": "ok", "id": entry_id, "agent_name": body.agent_name}
        except ValueError as exc:
            return validation_error(str(exc))

    @router.get("/api/v1/palace/diary/{agent}")
    async def palace_read_diary(agent: str, limit: int = 20):
        try:
            entries = _palace.read_diary(agent, limit=limit)
            return {"status": "ok", "agent_name": agent, "entries": entries, "count": len(entries)}
        except ValueError as exc:
            return validation_error(str(exc))

    @router.post("/api/v1/palace/agents")
    async def palace_provision_agent(body: PalaceProvisionAgentRequest):
        try:
            wing = _palace.ensure_agent_wing(body.name, description=body.description)
            return {"status": "ok", "wing": wing}
        except ValueError as exc:
            return validation_error(str(exc))

    @router.get("/api/v1/palace/agents")
    async def palace_list_agents():
        agents = _palace.list_agents()
        return {"status": "ok", "agents": agents, "total": len(agents)}

    return router
