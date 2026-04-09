from __future__ import annotations

import argparse

import pytest

from memos import MemOS
from memos.cli import cmd_extract_kg
from memos.kg_extractor import KGExtractor
from memos.knowledge_graph import KnowledgeGraph


@pytest.mark.parametrize(
    ("text", "predicate", "subject", "obj"),
    [
        ("Alice works at Acme Corp.", "works_at", "Alice", "Acme Corp"),
        ("Alice worked at Acme Corp.", "works_at", "Alice", "Acme Corp"),
        ("Alice working at Acme Corp.", "works_at", "Alice", "Acme Corp"),
        ("Alice travaille chez Acme Corp.", "works_at", "Alice", "Acme Corp"),
        ("Alice bosse pour Acme Corp.", "works_at", "Alice", "Acme Corp"),
        ("Alice is Platform Lead.", "is", "Alice", "Platform Lead"),
        ("Alice was Platform Lead.", "is", "Alice", "Platform Lead"),
        ("Alice est une Platform Lead.", "is", "Alice", "Platform Lead"),
        ("Atlas uses FastAPI.", "uses", "Atlas", "FastAPI"),
        ("Atlas used PostgreSQL.", "uses", "Atlas", "PostgreSQL"),
        ("Atlas runs on Kubernetes.", "uses", "Atlas", "Kubernetes"),
        ("Atlas built with ClickHouse.", "uses", "Atlas", "ClickHouse"),
        ("Atlas utilise FastAPI.", "uses", "Atlas", "FastAPI"),
        ("Atlas tourne sur Kubernetes.", "uses", "Atlas", "Kubernetes"),
        ("Atlas construit avec ClickHouse.", "uses", "Atlas", "ClickHouse"),
        ("Atlas deployed to Production Cluster.", "deployed_to", "Atlas", "Production Cluster"),
        ("Atlas deploys on Production Cluster.", "deployed_to", "Atlas", "Production Cluster"),
        ("Atlas shipped into Production Cluster.", "deployed_to", "Atlas", "Production Cluster"),
        ("Atlas a été déployé sur Production Cluster.", "deployed_to", "Atlas", "Production Cluster"),
        ("Atlas déployée dans Production Cluster.", "deployed_to", "Atlas", "Production Cluster"),
        ("Alice fixed Login Bug.", "fixed", "Alice", "Login Bug"),
        ("Alice resolved Login Bug.", "fixed", "Alice", "Login Bug"),
        ("Alice patched Login Bug.", "fixed", "Alice", "Login Bug"),
        ("Alice a corrigé Login Bug.", "fixed", "Alice", "Login Bug"),
        ("Alice a réparé Login Bug.", "fixed", "Alice", "Login Bug"),
        ("Alice a résolu Login Bug.", "fixed", "Alice", "Login Bug"),
    ],
)
def test_extract_explicit_patterns(text: str, predicate: str, subject: str, obj: str) -> None:
    extractor = KGExtractor()
    facts = extractor.extract(text)
    assert facts
    assert any(
        fact.predicate == predicate and fact.subject == subject and fact.object == obj and fact.confidence_label == "EXTRACTED"
        for fact in facts
    )


@pytest.mark.parametrize(
    "text",
    [
        "Alice does not work at Acme Corp.",
        "Alice ne travaille pas chez Acme Corp.",
        "Alice never used FastAPI.",
        "Alice n'utilise pas FastAPI.",
        "Atlas was not deployed to Production Cluster.",
        "Atlas n'a pas été déployé sur Production Cluster.",
        "Alice did not fix Login Bug.",
        "Alice n'a pas corrigé Login Bug.",
        "If Alice works at Acme Corp, update the docs.",
        "Si Alice travaille chez Acme Corp, mets à jour la doc.",
        "Alice could use FastAPI later.",
        "Alice pourrait utiliser FastAPI plus tard.",
    ],
)
def test_extract_skips_negated_and_conditional_sentences(text: str) -> None:
    extractor = KGExtractor()
    assert extractor.extract(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Alice joined Acme Corp team.", ("Alice", "related_to", "Acme Corp", "AMBIGUOUS")),
        ("Atlas with Kubernetes stack.", ("Atlas", "related_to", "Kubernetes", "AMBIGUOUS")),
        ("Alice dans Project Phoenix service.", ("Alice", "related_to", "Project Phoenix", "AMBIGUOUS")),
    ],
)
def test_extract_ambiguous_fallback(text: str, expected: tuple[str, str, str, str]) -> None:
    extractor = KGExtractor()
    facts = extractor.extract(text)
    assert len(facts) == 1
    fact = facts[0]
    assert (fact.subject, fact.predicate, fact.object, fact.confidence_label) == expected


def test_extract_deduplicates_repeated_facts() -> None:
    extractor = KGExtractor()
    facts = extractor.extract("Alice works at Acme Corp. Alice works at Acme Corp.")
    assert len(facts) == 1


def test_detect_entities_returns_unique_entities() -> None:
    extractor = KGExtractor()
    entities = extractor.detect_entities("Alice works at Acme Corp with Bob and Acme Corp")
    assert entities == ["Alice", "Acme Corp", "Bob"]


def test_extract_multiple_sentences() -> None:
    extractor = KGExtractor()
    facts = extractor.extract(
        "Alice works at Acme Corp. Atlas uses FastAPI. Atlas deployed to Production Cluster."
    )
    assert {fact.predicate for fact in facts} == {"works_at", "uses", "deployed_to"}


def test_memos_learn_auto_extracts_to_kg(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    memos = MemOS(backend="memory", persist_path=str(store_path), kg_db_path=str(kg_path))

    memos.learn("Alice works at Acme Corp")

    with KnowledgeGraph(db_path=str(kg_path)) as kg:
        facts = kg.query("Alice")
        assert len(facts) == 1
        assert facts[0]["predicate"] == "works_at"
        assert facts[0]["source"].startswith("memos:")
        assert facts[0]["confidence_label"] == "EXTRACTED"


def test_memos_learn_auto_kg_can_be_disabled_per_call(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    memos = MemOS(backend="memory", persist_path=str(store_path), kg_db_path=str(kg_path))

    memos.learn("Alice works at Acme Corp", auto_kg=False)

    with KnowledgeGraph(db_path=str(kg_path)) as kg:
        assert kg.query("Alice") == []


def test_memos_auto_kg_respects_env_toggle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEMOS_AUTO_KG", "false")
    store_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    memos = MemOS(backend="memory", persist_path=str(store_path), kg_db_path=str(kg_path))

    memos.learn("Alice works at Acme Corp")

    with KnowledgeGraph(db_path=str(kg_path)) as kg:
        assert kg.query("Alice") == []


def test_api_kg_extract_endpoint_returns_preview() -> None:
    from fastapi.testclient import TestClient
    from memos.api import create_fastapi_app

    app = create_fastapi_app(backend="memory", kg_db_path=":memory:")
    client = TestClient(app)

    response = client.post("/api/v1/kg/extract", json={"content": "Alice travaille chez Acme Corp"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["facts"][0]["predicate"] == "works_at"


def test_api_learn_auto_extracts_into_kg(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from memos.api import create_fastapi_app

    store_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    memos = MemOS(backend="memory", persist_path=str(store_path), kg_db_path=str(kg_path))
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))
    client = TestClient(app)

    response = client.post("/api/v1/learn", json={"content": "Alice works at Acme Corp"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    facts = client.get("/api/v1/kg/query", params={"entity": "Alice"}).json()["facts"]
    assert len(facts) == 1
    assert facts[0]["object"] == "Acme Corp"


def test_api_learn_auto_kg_false_skips_extraction(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from memos.api import create_fastapi_app

    store_path = tmp_path / "store.json"
    kg_path = tmp_path / "kg.db"
    memos = MemOS(backend="memory", persist_path=str(store_path), kg_db_path=str(kg_path))
    app = create_fastapi_app(memos=memos, kg_db_path=str(kg_path))
    client = TestClient(app)

    response = client.post("/api/v1/learn", json={"content": "Alice works at Acme Corp", "auto_kg": False})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    facts = client.get("/api/v1/kg/query", params={"entity": "Alice"}).json()["facts"]
    assert facts == []


def test_cli_extract_kg_outputs_json(capsys) -> None:
    ns = argparse.Namespace(content="Alice works at Acme Corp", json=True)
    cmd_extract_kg(ns)
    out = capsys.readouterr().out
    assert '"predicate": "works_at"' in out


def test_cli_extract_kg_outputs_text(capsys) -> None:
    ns = argparse.Namespace(content="Atlas uses FastAPI", json=False)
    cmd_extract_kg(ns)
    out = capsys.readouterr().out
    assert "Atlas -uses-> FastAPI" in out
