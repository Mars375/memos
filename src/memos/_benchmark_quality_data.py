"""Synthetic datasets for recall quality benchmarks."""

from __future__ import annotations

import random
from typing import Any

CATEGORIES: dict[str, list[str]] = {
    "person": [
        "Alice Chen is a senior ML engineer specializing in NLP",
        "Bob Martinez leads the infrastructure team at Acme Corp",
        "Carol Williams designed the microservices architecture",
        "David Park manages customer success operations",
        "Eva Schmidt researches reinforcement learning at DeepMind",
        "Frank Lee built the real-time data pipeline",
        "Grace Kim oversees security compliance audits",
        "Henry Zhang developed the recommendation engine",
        "Iris Johnson coordinates cross-team sprints",
        "Jack Brown maintains the CI/CD pipeline",
    ],
    "project": [
        "Project Phoenix migrates legacy Java services to Go microservices",
        "Project Atlas builds a unified data platform across teams",
        "Project Beacon implements real-time monitoring dashboards",
        "Project Catalyst upgrades the ML inference pipeline to GPU",
        "Project Delta redesigns the customer onboarding flow",
        "Project Echo adds end-to-end encryption to all API endpoints",
        "Project Falcon deploys edge computing nodes in 5 regions",
        "Project Gamma refactors the billing system for multi-currency",
        "Project Helios integrates solar panel telemetry data",
        "Project Ion develops quantum-resistant cryptography modules",
    ],
    "decision": [
        "Decided to use PostgreSQL over MongoDB for transactional data integrity",
        "Chose Kubernetes over Nomad for container orchestration standardization",
        "Adopted TypeScript instead of JavaScript for type safety at scale",
        "Selected gRPC for internal services, REST for external APIs",
        "Moved from Jenkins to GitHub Actions for CI/CD modernization",
        "Switched to RUST for the performance-critical data parser module",
        "Approved React Server Components for the new dashboard frontend",
        "Decided on event-driven architecture using Apache Kafka",
        "Chose Terraform over CloudFormation for multi-cloud IaC",
        "Adopted OIDC with SSO for unified authentication across services",
    ],
    "preference": [
        "Prefer dark mode interfaces with monospace fonts for readability",
        "Always use conventional commits with scope prefixes",
        "Prefer async communication over synchronous meetings",
        "Code reviews should be completed within 24 hours maximum",
        "Use semantic versioning with prerelease tags for beta features",
        "Prefer horizontal scaling over vertical for all stateless services",
        "Documentation should live alongside code in docs/ directories",
        "Prefer managed services over self-hosted for non-core infrastructure",
        "All APIs must have OpenAPI specs generated at build time",
        "Use feature flags for gradual rollouts to production",
    ],
    "incident": [
        "Outage on 2025-03-15: Redis cluster failed over, 12min downtime",
        "Memory leak in auth-service caused OOM kills every 6 hours",
        "SSL certificate expired on staging, blocking deploys for 4 hours",
        "Database migration locked production users table for 8 minutes",
        "CDN misconfiguration served stale assets to 30% of users",
        "DNS propagation delay caused regional outage in APAC zone",
        "Rate limiter bug blocked legitimate traffic at 1000 req/s",
        "Backup restore took 3 hours due to uncompressed snapshots",
        "Load balancer health check timeout too aggressive during peak",
        "Third-party API deprecation broke payment processing module",
    ],
}

QUERY_TEMPLATES: list[dict[str, Any]] = [
    {
        "query": "Who works on machine learning?",
        "category": "person",
        "expected_keywords": ["Alice", "ML", "NLP", "Eva", "reinforcement"],
    },
    {
        "query": "What is Project Phoenix about?",
        "category": "project",
        "expected_keywords": ["Phoenix", "Java", "Go", "microservices", "migrate"],
    },
    {
        "query": "Why did we choose PostgreSQL?",
        "category": "decision",
        "expected_keywords": ["PostgreSQL", "MongoDB", "transactional", "integrity"],
    },
    {
        "query": "What are the coding preferences?",
        "category": "preference",
        "expected_keywords": ["commits", "code review", "dark mode", "monospace"],
    },
    {
        "query": "What was the Redis incident?",
        "category": "incident",
        "expected_keywords": ["Redis", "outage", "downtime", "cluster", "failover"],
    },
    {
        "query": "Who built the data pipeline?",
        "category": "person",
        "expected_keywords": ["Frank", "data pipeline", "real-time"],
    },
    {
        "query": "Tell me about Project Atlas",
        "category": "project",
        "expected_keywords": ["Atlas", "data platform", "unified"],
    },
    {
        "query": "Why gRPC for internal services?",
        "category": "decision",
        "expected_keywords": ["gRPC", "REST", "internal", "external"],
    },
    {
        "query": "How do we handle code reviews?",
        "category": "preference",
        "expected_keywords": ["code review", "24 hours", "review"],
    },
    {
        "query": "What happened with the SSL certificate?",
        "category": "incident",
        "expected_keywords": ["SSL", "certificate", "staging", "expired"],
    },
    {
        "query": "Who handles security?",
        "category": "person",
        "expected_keywords": ["Grace", "security", "compliance", "audit"],
    },
    {"query": "What does Project Echo do?", "category": "project", "expected_keywords": ["Echo", "encryption", "API"]},
    {
        "query": "Why Kubernetes over Nomad?",
        "category": "decision",
        "expected_keywords": ["Kubernetes", "Nomad", "orchestration"],
    },
    {
        "query": "What is our scaling strategy?",
        "category": "preference",
        "expected_keywords": ["horizontal", "scaling", "stateless"],
    },
    {
        "query": "What caused the database migration issue?",
        "category": "incident",
        "expected_keywords": ["database", "migration", "locked", "users"],
    },
    {
        "query": "Who designed the architecture?",
        "category": "person",
        "expected_keywords": ["Carol", "microservices", "architecture"],
    },
    {
        "query": "Project Beacon monitoring",
        "category": "project",
        "expected_keywords": ["Beacon", "monitoring", "dashboard"],
    },
    {
        "query": "Why did we adopt TypeScript?",
        "category": "decision",
        "expected_keywords": ["TypeScript", "JavaScript", "type safety"],
    },
    {
        "query": "What CI/CD tool do we use?",
        "category": "decision",
        "expected_keywords": ["GitHub Actions", "Jenkins", "CI/CD"],
    },
    {
        "query": "DNS outage in Asia Pacific",
        "category": "incident",
        "expected_keywords": ["DNS", "APAC", "outage", "propagation"],
    },
]


def generate_dataset(
    memories_per_category: int = 10,
    extra_noise: int = 50,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate a synthetic dataset with ground truth."""
    rng = random.Random(seed)
    memories: list[dict[str, Any]] = []

    for category, templates in CATEGORIES.items():
        for index, template in enumerate(templates[:memories_per_category]):
            memories.append(
                {
                    "content": template,
                    "tags": [category],
                    "importance": 0.3 + rng.random() * 0.6,
                    "category": category,
                    "idx": index,
                }
            )

    noise_topics = [
        "weather forecast shows rain tomorrow afternoon",
        "grocery list: milk, eggs, bread, avocados, cheese",
        "the movie starts at 8pm at the downtown theater",
        "flight UA-456 departs from gate B12 at terminal 2",
        "restaurant reservation for 7 people on Saturday evening",
        "yoga class is cancelled this week due to renovation",
        "car oil change scheduled for next Tuesday morning",
        "book club meeting discusses chapter 5 of the novel",
        "garden tomatoes are ready for harvest this weekend",
        "local park has a new running trail about 3km long",
    ]
    for index in range(extra_noise):
        topic = noise_topics[index % len(noise_topics)]
        memories.append(
            {
                "content": f"{topic} — note #{index + 1}",
                "tags": ["noise"],
                "importance": 0.2 + rng.random() * 0.3,
                "category": "noise",
                "idx": index,
            }
        )

    return memories, QUERY_TEMPLATES


__all__ = ["CATEGORIES", "QUERY_TEMPLATES", "generate_dataset"]
