"""Health and diagnostics tools: alerts, events, resource quotas, limit ranges."""

from kubernetes import client


def register(mcp, cluster_alerts: dict):
    """Register diagnostics tools. Receives shared cluster_alerts dict from KOPF."""
    v1 = client.CoreV1Api()

    @mcp.tool()
    def get_active_alerts() -> str:
        """Check if the background monitor has captured any pod crash alerts. Returns a list or an all-clear message."""
        if not cluster_alerts:
            return "✅ Cluster is stable. No critical alerts detected recently."
        report = "🚨 CRITICAL ALERTS DETECTED:\n"
        for k, v in cluster_alerts.items():
            report += (
                f"  - Pod: {v['pod']}  |  Namespace: {v['namespace']}  "
                f"|  Reason: {v['reason']}  |  Exit Code: {v['exit_code']}\n"
            )
        return report

    @mcp.tool()
    def get_recent_events(namespace: str = "default") -> str:
        """List the most recent Warning-type Kubernetes events in a namespace."""
        try:
            events = v1.list_namespaced_event(namespace=namespace, field_selector="type=Warning")
            if not events.items:
                return f"No Warning events in namespace '{namespace}'."
            lines = []
            for e in events.items[-15:]:
                count = e.count or 1
                lines.append(
                    f"  [{e.reason}] {e.involved_object.kind}/{e.involved_object.name}: "
                    f"{e.message}  (x{count})"
                )
            return f"WARNING EVENTS in '{namespace}' (last {len(lines)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error fetching events: {e}"

    @mcp.tool()
    def get_all_events(namespace: str = "default") -> str:
        """Retrieve all recent events (Normal + Warning) in a namespace."""
        try:
            events = v1.list_namespaced_event(namespace=namespace)
            if not events.items:
                return f"No events in namespace '{namespace}'."
            lines = []
            for e in events.items[-20:]:
                lines.append(
                    f"  [{e.type}] [{e.reason}] {e.involved_object.kind}/{e.involved_object.name}: "
                    f"{e.message}"
                )
            return f"ALL EVENTS in '{namespace}' (last {len(lines)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error fetching events: {e}"

    @mcp.tool()
    def list_resource_quotas(namespace: str = "default") -> str:
        """List ResourceQuotas in a namespace showing used vs hard limits."""
        try:
            rqs = v1.list_namespaced_resource_quota(namespace=namespace)
            if not rqs.items:
                return f"No ResourceQuotas in namespace '{namespace}'."
            lines = []
            for rq in rqs.items:
                lines.append(f"  QUOTA: {rq.metadata.name}")
                hard = rq.status.hard or {}
                used = rq.status.used or {}
                for resource in sorted(hard.keys()):
                    h = hard.get(resource, "?")
                    u = used.get(resource, "0")
                    lines.append(f"    {resource}: {u} / {h}")
            return f"RESOURCE QUOTAS in '{namespace}' ({len(rqs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing resource quotas: {e}"

    @mcp.tool()
    def list_limit_ranges(namespace: str = "default") -> str:
        """List LimitRanges in a namespace showing default/max/min container limits."""
        try:
            lrs = v1.list_namespaced_limit_range(namespace=namespace)
            if not lrs.items:
                return f"No LimitRanges in namespace '{namespace}'."
            lines = []
            for lr in lrs.items:
                lines.append(f"  LIMIT RANGE: {lr.metadata.name}")
                for item in lr.spec.limits or []:
                    lines.append(f"    Type: {item.type}")
                    if item.default:
                        lines.append(f"      Default limits: {dict(item.default)}")
                    if item.default_request:
                        lines.append(f"      Default requests: {dict(item.default_request)}")
                    if item.max:
                        lines.append(f"      Max: {dict(item.max)}")
                    if item.min:
                        lines.append(f"      Min: {dict(item.min)}")
            return f"LIMIT RANGES in '{namespace}' ({len(lrs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing limit ranges: {e}"
