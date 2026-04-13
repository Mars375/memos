"""MemOS CLI — namespace, sharing, sync commands."""

from __future__ import annotations

import argparse
import json

from ._common import _get_memos


def cmd_ns_grant(ns: argparse.Namespace) -> None:
    """Grant an agent access to a namespace."""
    memos = _get_memos(ns)
    policy = memos.grant_namespace_access(
        agent_id=ns.agent,
        namespace=ns.namespace,
        role=ns.role,
        expires_at=ns.expires,
    )
    print(f"✓ Granted {ns.role} access to '{ns.namespace}' for agent '{ns.agent}'")
    if ns.json if hasattr(ns, "json") else False:
        print(json.dumps(policy, indent=2))


def cmd_ns_revoke(ns: argparse.Namespace) -> None:
    """Revoke an agent's namespace access."""
    memos = _get_memos(ns)
    success = memos.revoke_namespace_access(
        agent_id=ns.agent,
        namespace=ns.namespace,
    )
    print(f"✓ Revoked access to '{ns.namespace}' for agent '{ns.agent}'" if success else "✗ No policy found")


def cmd_ns_policies(ns: argparse.Namespace) -> None:
    """List namespace ACL policies."""
    memos = _get_memos(ns)
    policies = memos.list_namespace_policies(namespace=getattr(ns, "namespace", None))
    if getattr(ns, "json", False):
        print(json.dumps(policies, indent=2))
        return
    if not policies:
        print("No policies found")
        return
    for p in policies:
        expires = f" (expires: {p['expires_at']})" if p.get("expires_at") else ""
        print(f"  {p['agent_id']}  {p['namespace']}  {p['role']}{expires}")
    print(f"\n{len(policies)} policy(ies)")


def cmd_ns_stats(ns: argparse.Namespace) -> None:
    """Show namespace ACL statistics."""
    memos = _get_memos(ns)
    stats = memos.namespace_acl_stats()
    if getattr(ns, "json", False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Total policies:  {stats['total_policies']}")
    print(f"  Total agents:    {stats['total_agents']}")
    print(f"  Total namespaces:{stats['total_namespaces']}")
    if stats.get("role_distribution"):
        for role, count in stats["role_distribution"].items():
            print(f"    {role}: {count}")


def cmd_share_offer(ns: argparse.Namespace) -> None:
    """Offer to share memories with another agent."""
    from ..sharing.models import SharePermission, ShareScope

    memos = _get_memos(ns)
    import time as _time

    expires = ns.expires
    if expires is not None:
        expires = _time.time() + expires
    req = memos.share_with(
        ns.target,
        scope=ShareScope(ns.scope),
        scope_key=ns.scope_key,
        permission=SharePermission(ns.permission),
        expires_at=expires,
    )
    print(f"Share offer created: {req.id}")
    print(f"  Source:  {req.source_agent}")
    print(f"  Target:  {req.target_agent}")
    print(f"  Scope:   {req.scope.value} ({req.scope_key})")
    print(f"  Perm:    {req.permission.value}")
    print(f"  Status:  {req.status.value}")


def cmd_share_accept(ns: argparse.Namespace) -> None:
    """Accept a pending share."""
    memos = _get_memos(ns)
    req = memos.accept_share(ns.share_id)
    print(f"Share accepted: {req.id}")
    print(f"  {req.source_agent} → {req.target_agent} ({req.scope.value})")


def cmd_share_reject(ns: argparse.Namespace) -> None:
    """Reject a pending share."""
    memos = _get_memos(ns)
    req = memos.reject_share(ns.share_id)
    print(f"Share rejected: {req.id}")


def cmd_share_revoke(ns: argparse.Namespace) -> None:
    """Revoke a share."""
    memos = _get_memos(ns)
    req = memos.revoke_share(ns.share_id)
    print(f"Share revoked: {req.id}")


def cmd_share_export(ns: argparse.Namespace) -> None:
    """Export memories for a share."""
    memos = _get_memos(ns)
    envelope = memos.export_shared(ns.share_id)
    data = envelope.to_dict()
    output = json.dumps(data, indent=2, default=str)
    if ns.output:
        with open(ns.output, "w") as f:
            f.write(output)
        print(f"Exported {len(envelope.memories)} memories to {ns.output}")
    else:
        print(output)


def cmd_share_import(ns: argparse.Namespace) -> None:
    """Import memories from an envelope file."""
    from ..sharing.models import MemoryEnvelope

    with open(ns.input_file, "r") as f:
        data = json.load(f)
    envelope = MemoryEnvelope.from_dict(data)
    memos = _get_memos(ns)
    learned = memos.import_shared(envelope)
    print(f"Imported {len(learned)} memories from {envelope.source_agent}")
    for item in learned[:10]:
        print(f"  {item.id}: {item.content[:60]}...")
    if len(learned) > 10:
        print(f"  ... and {len(learned) - 10} more")


def cmd_share_list(ns: argparse.Namespace) -> None:
    """List shares."""
    from ..sharing.models import ShareStatus

    memos = _get_memos(ns)
    status = ShareStatus(ns.status) if ns.status else None
    shares = memos.list_shares(agent=ns.agent, status=status)
    if getattr(ns, "json", False):
        print(json.dumps([s.to_dict() for s in shares], indent=2, default=str))
        return
    if not shares:
        print("No shares found")
        return
    print(f"Shares ({len(shares)}):")
    for s in shares:
        print(
            f"  {s.id}  {s.source_agent} → {s.target_agent}  [{s.status.value}]  scope={s.scope.value}({s.scope_key})"
        )


def cmd_share_stats(ns: argparse.Namespace) -> None:
    """Show sharing statistics."""
    memos = _get_memos(ns)
    stats = memos.sharing_stats()
    if getattr(ns, "json", False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Total shares:     {stats['total_shares']}")
    print(f"  Active shares:    {stats['active_shares']}")
    print(f"  Pending shares:   {stats['pending_shares']}")
    print(f"  Total agents:     {stats['total_agents']}")
    for status, count in stats.get("status_distribution", {}).items():
        print(f"    {status}: {count}")


def cmd_sync_check(ns: argparse.Namespace) -> None:
    """Check for conflicts between local store and a remote export file."""
    from ..conflict import ConflictDetector
    from ..sharing.models import MemoryEnvelope

    memos = _get_memos(ns)
    path = ns.remote_file
    with open(path) as f:
        data = json.load(f)

    envelope = MemoryEnvelope.from_dict(data)
    if not envelope.validate():
        print("✗ Envelope checksum validation failed — data may be corrupted")
        return

    detector = ConflictDetector()
    report = detector.detect(memos, envelope)

    if getattr(ns, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"Sync check: {report.total_remote} remote memories")
    print(f"  New (no conflict):  {report.new_memories}")
    print(f"  Unchanged:          {report.unchanged}")
    print(f"  Conflicts:          {len(report.conflicts)}")
    if report.errors:
        print(f"  Errors:             {len(report.errors)}")
        for e in report.errors[:5]:
            print(f"    - {e}")

    if report.conflicts:
        print()
        for c in report.conflicts:
            types = ", ".join(t.value for t in c.conflict_types)
            print(f"  ⚠ {c.memory_id[:12]}… [{types}]")
            if c.local_content != c.remote_content:
                print(f"    local:  {c.local_content[:80]}")
                print(f"    remote: {c.remote_content[:80]}")
            if c.local_tags != c.remote_tags:
                print(f"    tags: {c.local_tags} → {c.remote_tags}")
            if abs(c.local_importance - c.remote_importance) > 0.01:
                print(f"    importance: {c.local_importance:.2f} → {c.remote_importance:.2f}")


def cmd_sync_apply(ns: argparse.Namespace) -> None:
    """Apply remote memories with conflict resolution."""
    from ..conflict import ConflictDetector, ResolutionStrategy
    from ..sharing.models import MemoryEnvelope

    memos = _get_memos(ns)
    path = ns.remote_file
    strategy = ResolutionStrategy(ns.strategy)

    with open(path) as f:
        data = json.load(f)

    envelope = MemoryEnvelope.from_dict(data)
    if not envelope.validate():
        print("✗ Envelope checksum validation failed — aborting")
        return

    detector = ConflictDetector()
    report = detector.detect(memos, envelope)

    if getattr(ns, "dry_run", False):
        detector.resolve(report.conflicts, strategy)
        if getattr(ns, "json", False):
            out = report.to_dict()
            out["dry_run"] = True
            print(json.dumps(out, indent=2))
            return
        print(f"Dry run — strategy: {strategy.value}")
        print(f"  Conflicts to resolve: {len(report.conflicts)}")
        print(f"  New memories to add:  {report.new_memories}")
        for c in report.conflicts:
            types = ", ".join(t.value for t in c.conflict_types)
            res = c.resolution.value if c.resolution else "none"
            print(f"  {c.memory_id[:12]}… [{types}] → {res}")
        return

    report = detector.apply(memos, report, strategy)

    if getattr(ns, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"✓ Sync applied — strategy: {strategy.value}")
    print(f"  Remote memories:  {report.total_remote}")
    print(f"  Applied:          {report.applied}")
    print(f"  Skipped:          {report.skipped}")
    print(f"  Conflicts:        {len(report.conflicts)}")
    if report.errors:
        print(f"  Errors:           {len(report.errors)}")
        for e in report.errors[:5]:
            print(f"    - {e}")
