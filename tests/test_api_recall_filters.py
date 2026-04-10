from fastapi.testclient import TestClient

from memos.api import create_fastapi_app
from memos.core import MemOS


def _seed_memories(mem: MemOS) -> None:
    mem.learn("critical project launch", tags=["project", "urgent"], importance=0.95)
    mem.learn("archived project launch", tags=["project", "urgent", "archived"], importance=0.9)
    mem.learn("casual cooking note", tags=["food"], importance=0.2)


def test_recall_endpoint_supports_structured_filters():
    mem = MemOS(backend="memory")
    mem._retrieval._store = mem._store
    _seed_memories(mem)
    client = TestClient(create_fastapi_app(memos=mem))

    resp = client.post(
        "/api/v1/recall",
        json={
            "query": "project launch",
            "top_k": 10,
            "tags": {
                "include": ["project"],
                "require": ["urgent"],
                "exclude": ["archived"],
            },
            "importance": {"min": 0.8},
            "retrieval_mode": "keyword",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert [item["content"] for item in data["results"]] == ["critical project launch"]
    assert data["results"][0]["importance"] == 0.95


def test_list_memories_endpoint_supports_sorting_and_filters():
    mem = MemOS(backend="memory")
    mem._retrieval._store = mem._store
    _seed_memories(mem)
    client = TestClient(create_fastapi_app(memos=mem))

    resp = client.get(
        "/api/v1/memories",
        params=[
            ("tag", "project"),
            ("require_tag", "urgent"),
            ("exclude_tag", "archived"),
            ("min_importance", "0.5"),
            ("sort", "importance"),
        ],
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total"] == 1
    assert data["results"][0]["content"] == "critical project launch"
