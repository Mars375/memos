"""Namespace ACL commands: ns-grant, ns-revoke, ns-policies, ns-stats."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # ns-grant
    ns_grant = sub.add_parser("ns-grant", help="Grant an agent access to a namespace")
    ns_grant.add_argument("namespace", help="Target namespace")
    ns_grant.add_argument("--agent", required=True, help="Agent ID")
    ns_grant.add_argument("--role", required=True, choices=["owner", "writer", "reader", "denied"], help="Access role")
    ns_grant.add_argument("--expires", type=float, default=None, help="Expires at (epoch timestamp)")
    _add_backend_arg(ns_grant)

    # ns-revoke
    ns_revoke = sub.add_parser("ns-revoke", help="Revoke an agent's namespace access")
    ns_revoke.add_argument("namespace", help="Target namespace")
    ns_revoke.add_argument("--agent", required=True, help="Agent ID")
    _add_backend_arg(ns_revoke)

    # ns-policies
    ns_list = sub.add_parser("ns-policies", help="List namespace ACL policies")
    ns_list.add_argument("--namespace", help="Filter by namespace")
    ns_list.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(ns_list)

    # ns-stats
    ns_stats = sub.add_parser("ns-stats", help="Show namespace ACL statistics")
    ns_stats.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(ns_stats)
