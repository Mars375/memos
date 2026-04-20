"""Knowledge graph commands: kg-add, kg-query, kg-timeline, kg-invalidate, kg-stats, kg-path, kg-neighbors, kg-infer, kg-labels, kg-lint, kg-backlinks."""

from __future__ import annotations


def build(sub) -> None:
    # kg-add
    kg_add = sub.add_parser("kg-add", help="Add a fact to the knowledge graph")
    kg_add.add_argument("subject", help="Subject entity")
    kg_add.add_argument("predicate", help="Relation type")
    kg_add.add_argument("object", help="Object entity or value")
    kg_add.add_argument(
        "--from", dest="valid_from", default=None, help="Valid from (epoch, ISO 8601, or relative e.g. 2d)"
    )
    kg_add.add_argument("--to", dest="valid_to", default=None, help="Valid to (epoch, ISO 8601, or relative)")
    kg_add.add_argument("--confidence", type=float, default=1.0, help="Confidence 0.0-1.0 (default 1.0)")
    kg_add.add_argument("--source", default=None, help="Source label")
    kg_add.add_argument(
        "--label",
        dest="confidence_label",
        default="EXTRACTED",
        choices=["EXTRACTED", "INFERRED", "AMBIGUOUS"],
        help="Confidence label (default: EXTRACTED)",
    )
    kg_add.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-query
    kg_query = sub.add_parser("kg-query", help="Query facts about an entity")
    kg_query.add_argument("entity", help="Entity name")
    kg_query.add_argument("--at", dest="at_time", default=None, help="Point in time (epoch, ISO 8601, or relative)")
    kg_query.add_argument("--direction", choices=["both", "subject", "object"], default="both")
    kg_query.add_argument("--db", dest="kg_db", default=None)

    # kg-timeline
    kg_tl = sub.add_parser("kg-timeline", help="Show chronological facts about an entity")
    kg_tl.add_argument("entity", help="Entity name")
    kg_tl.add_argument("--db", dest="kg_db", default=None)

    # kg-invalidate
    kg_inv = sub.add_parser("kg-invalidate", help="Invalidate (expire) a fact by ID")
    kg_inv.add_argument("fact_id", help="Fact ID to invalidate")
    kg_inv.add_argument("--db", dest="kg_db", default=None)

    # kg-stats
    kg_stats = sub.add_parser("kg-stats", help="Show knowledge graph statistics")
    kg_stats.add_argument("--db", dest="kg_db", default=None)

    # kg-path
    kg_path = sub.add_parser("kg-path", help="Find paths between two entities")
    kg_path.add_argument("entity_a", help="Start entity")
    kg_path.add_argument("entity_b", help="Target entity")
    kg_path.add_argument("--max-hops", type=int, default=3, help="Max hops (default: 3)")
    kg_path.add_argument("--max-paths", type=int, default=10, help="Max paths to return (default: 10)")
    kg_path.add_argument("--db", dest="kg_db", default=None)

    # kg-neighbors
    kg_nbrs = sub.add_parser("kg-neighbors", help="Show entity neighborhood")
    kg_nbrs.add_argument("entity", help="Entity name")
    kg_nbrs.add_argument("--depth", type=int, default=1, help="Neighborhood depth (default: 1)")
    kg_nbrs.add_argument("--direction", choices=["both", "subject", "object"], default="both")
    kg_nbrs.add_argument("--db", dest="kg_db", default=None)

    # kg-infer
    kg_infer = sub.add_parser("kg-infer", help="Infer transitive facts for a predicate")
    kg_infer.add_argument("predicate", help="Predicate to infer transitivity on (e.g. 'manages')")
    kg_infer.add_argument(
        "--as",
        dest="inferred_predicate",
        default=None,
        help="Name for inferred predicate (default: <predicate>_transitive)",
    )
    kg_infer.add_argument("--max-depth", type=int, default=3, help="Max inference depth (default: 3)")
    kg_infer.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-labels
    kg_labels = sub.add_parser("kg-labels", help="Show facts by confidence label")
    kg_labels.add_argument(
        "label", choices=["EXTRACTED", "INFERRED", "AMBIGUOUS"], help="Confidence label to filter by"
    )
    kg_labels.add_argument("--all", dest="show_all", action="store_true", help="Include invalidated facts")
    kg_labels.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-lint
    kg_lint = sub.add_parser("kg-lint", help="Lint the KG — find contradictions, orphans, sparse entities")
    kg_lint.add_argument(
        "--min-facts", dest="min_facts", type=int, default=2, help="Minimum active facts per entity (default: 2)"
    )
    kg_lint.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-backlinks
    kg_backlinks = sub.add_parser("kg-backlinks", help="Show incoming edges (backlinks) for an entity")
    kg_backlinks.add_argument("entity", help="Entity name to find backlinks for")
    kg_backlinks.add_argument("--predicate", default=None, help="Filter by predicate")
    kg_backlinks.add_argument("--all", dest="show_all", action="store_true", help="Include invalidated facts")
    kg_backlinks.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")
