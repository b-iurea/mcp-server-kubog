"""Health and diagnostics tools: alerts, events, resource quotas, limit ranges."""

from kubernetes import client
from tools.utils import sanitize_for_ai, to_compact_yaml, truncate_logs


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
    def get_diagnostic_context(name: str, namespace: str = "default", rtype: str = "pod") -> str:
        """Fetch detailed logs, events, and resource info for a specific resource."""
        context = f"Diagnostic report for {rtype}/{name} in {namespace}:\n\n"
        rtype_lower = rtype.lower()
        if 'pod' in rtype_lower:
            # 1. Fetch Pod Details & Limits
            try:
                pod = v1.read_namespaced_pod(name, namespace)
                context += "--- POD DETAILS ---\n"
                context += f"Node Assigned: {pod.spec.node_name}\n"
                for c in pod.spec.containers:
                    req = c.resources.requests if c.resources and c.resources.requests else {}
                    lim = c.resources.limits if c.resources and c.resources.limits else {}
                    context += f"Container '{c.name}': Req({req}) | Lim({lim})\n"
            except Exception as e:
                context += f"Failed to read pod details: {e}\n"

            # 2. Fetch Warning Events for Pod
            try:
                events = v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name},type=Warning")
                context += "\n--- WARNING EVENTS ---\n"
                if not events.items:
                    context += "No warning events found.\n"
                for e in events.items[-3:]:  # Cap to 3 events to save tokens
                    context += f"[{e.reason}] {e.message} (x{e.count or 1})\n"
            except Exception as e:
                context += f"Failed to fetch events: {e}\n"

            # 3. Fetch Previous Logs
            try:
                prev_logs = v1.read_namespaced_pod_log(name, namespace, previous=True, tail_lines=50)
                context += "\n--- PREVIOUS LOGS (from before crash) ---\n"
                context += truncate_logs(prev_logs, max_chars=1500) if prev_logs else "Empty."
                context += "\n"
            except Exception as e:
                context += f"\n--- PREVIOUS LOGS ---\nUnavailable or pod hasn't restarted yet. ({e})\n"

            # 4. Fetch Current Logs
            try:
                curr_logs = v1.read_namespaced_pod_log(name, namespace, tail_lines=50)
                context += "\n--- CURRENT LOGS ---\n"
                context += truncate_logs(curr_logs, max_chars=1500) if curr_logs else "Empty."
                context += "\n"
            except Exception:
                context += "\n--- CURRENT LOGS ---\nUnavailable.\n"

        elif 'node' in rtype_lower:
            # 1. Fetch Node Details
            try:
                node = v1.read_node(name)
                context += "--- NODE DETAILS ---\n"
                context += f"Allocatable: {node.status.allocatable}\n"
                context += f"Capacity: {node.status.capacity}\n"
                context += "\n--- CONDITIONS ---\n"
                for c in node.status.conditions:
                    context += f"[{c.type}] Status: {c.status} | Reason: {c.reason} | Msg: {c.message}\n"
            except Exception as e:
                context += f"Failed to read node details: {e}\n"
                
            # 2. Fetch Events for Node
            try:
                events = v1.list_event_for_all_namespaces(field_selector=f"involvedObject.name={name},type=Warning")
                context += "\n--- WARNING EVENTS ---\n"
                if not events.items:
                    context += "No warning events found.\n"
                for e in events.items[-3:]:
                    context += f"[{e.reason}] {e.message} (x{e.count or 1})\n"
            except Exception as e:
                context += f"Failed to fetch events: {e}\n"
        
        else:
            context += f"Unsupported resource type: {rtype}. Use 'pod' or 'node'."

        return context

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
