"""Health and diagnostics tools: alerts, events, resource quotas, limit ranges."""

from kubernetes import client
from tools.utils import sanitize_for_ai, to_compact_yaml, truncate_logs


def register(mcp, cluster_alerts: dict):
    """Register diagnostics tools. Receives shared cluster_alerts dict from KOPF."""
    v1 = client.CoreV1Api()
    apps = client.AppsV1Api()

    @mcp.tool()
    def generate_cluster_report() -> str:
        """
        Generate a comprehensive high-level report of the entire cluster state.
        Includes node health, aggregated pod status, deployment health, active critical alerts, and recent cluster-wide warning events.
        Use this tool first to get a birds-eye view before diving into specific resources.
        """
        report = "=== CLUSTER HEALTH REPORT ===\n\n"

        # 1. Nodes Check
        try:
            nodes = v1.list_node().items
            ready = sum(1 for n in nodes if any(c.type == 'Ready' and c.status == 'True' for c in n.status.conditions))
            report += f"🖥️  NODES: {ready}/{len(nodes)} Ready\n"
        except Exception as e:
            report += f"🖥️  NODES: Error fetching ({e})\n"

        # 2. Deployments Check
        try:
            deps = apps.list_deployment_for_all_namespaces().items
            ready_deps = sum(1 for d in deps if d.status.ready_replicas == d.status.replicas)
            report += f"📦 DEPLOYMENTS: {ready_deps}/{len(deps)} fully rolled out\n"
        except Exception as e:
            report += f"📦 DEPLOYMENTS: Error fetching ({e})\n"

        # 3. Pods Aggregation
        try:
            pods = v1.list_pod_for_all_namespaces().items
            phases = {}
            for p in pods:
                phase = p.status.phase
                phases[phase] = phases.get(phase, 0) + 1
            pod_stats = ", ".join(f"{count} {phase}" for phase, count in phases.items())
            report += f"🐳 PODS: {len(pods)} Total ({pod_stats})\n"
        except Exception as e:
            report += f"🐳 PODS: Error fetching ({e})\n"

        # 4. Active Alerts
        report += "\n🚨 ACTIVE CRITICAL ALERTS:\n"
        if not cluster_alerts:
            report += "   None. Cluster is stable.\n"
        else:
            for k, v in cluster_alerts.items():
                if v.get("type") == "PodAlert":
                    report += f"   - [POD] {v['pod']} ({v['namespace']}): {v['reason']}\n"
                elif v.get("type") == "NodeAlert":
                    report += f"   - [NODE] {v['node']}: {v['reason']}\n"
                else:
                    report += f"   - {k}\n"

        # 5. Recent Warning Events
        report += "\n⚠️  RECENT WARNING EVENTS (Last 5):\n"
        try:
            events = v1.list_event_for_all_namespaces(field_selector="type=Warning").items
            if not events:
                report += "   No recent warnings.\n"
            else:
                for e in events[-5:]:
                    report += f"   - [{e.reason}] {e.involved_object.kind}/{e.involved_object.name}: {e.message} (x{e.count or 1})\n"
        except Exception as e:
            report += f"   Error fetching events ({e})\n"

        return report

    @mcp.tool()
    def get_active_alerts() -> str:
        """Check if the background monitor has captured any pod crash alerts or node distress alerts. Returns a list or an all-clear message."""
        if not cluster_alerts:
            return "✅ Cluster is stable. No critical alerts detected recently."
        report = "🚨 CRITICAL ALERTS DETECTED:\n"
        for k, v in cluster_alerts.items():
            atype = v.get("type")
            if atype == "PodAlert":
                report += (
                    f"  - [POD] {v['pod']}  |  Namespace: {v['namespace']}  "
                    f"|  Reason: {v['reason']}  |  Exit Code: {v['exit_code']}  | Msg: {v.get('message', '')}\n"
                )
            elif atype == "NodeAlert":
                report += (
                    f"  - [NODE] {v['node']}  |  Condition: {v['reason']}  |  Msg: {v.get('message', '')}\n"
                )
            else:
                # Fallback for old formatting if any
                report += f"  - Alert: {v}\n"
        return report

    @mcp.tool()
    def get_diagnostic_context(resource_type: str, name: str, namespace: str = "default") -> str:
        """
        Gather an extensive context blob for a given resource (pod or node) to perform Root Cause Analysis.
        Use this tool when you detect an alert and need to understand WHY it happened.
        For pods, it fetches previous logs, current logs, warning events, and resource limits.
        For nodes, it fetches conditions, capacity, and warning events.
        """
        context = f"=== DIAGNOSTIC CONTEXT FOR {resource_type.upper()}: {name} ===\n\n"
        
        rtype_lower = resource_type.lower()
        if 'pod' in rtype_lower:
            # 1. Fetch Pod Details & Limits
            try:
                pod = v1.read_namespaced_pod(name, namespace)
                context += "--- POD DETAILS ---\n"
                context += f"Node Assigned: {pod.spec.node_name}\n"
                for c in pod.spec.containers:
                    context += f"Container '{c.name}' Resources: {c.resources.to_dict()}\n"
            except Exception as e:
                context += f"Failed to read pod details: {e}\n"

            # 2. Fetch Warning Events for Pod
            try:
                events = v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name},type=Warning")
                context += "\n--- WARNING EVENTS ---\n"
                if not events.items:
                    context += "No warning events found.\n"
                for e in events.items[-5:]:
                    context += f"[{e.reason}] {e.message} (x{e.count or 1})\n"
            except Exception as e:
                context += f"Failed to fetch events: {e}\n"

            # 3. Fetch Previous Logs
            try:
                prev_logs = v1.read_namespaced_pod_log(name, namespace, previous=True, tail_lines=50)
                context += "\n--- PREVIOUS LOGS (from before crash) ---\n"
                context += prev_logs[-1000:] if prev_logs else "Empty."
                context += "\n"
            except Exception as e:
                context += f"\n--- PREVIOUS LOGS ---\nUnavailable or pod hasn't restarted yet. ({e})\n"

            # 4. Fetch Current Logs
            try:
                curr_logs = v1.read_namespaced_pod_log(name, namespace, tail_lines=50)
                context += "\n--- CURRENT LOGS ---\n"
                context += curr_logs[-1000:] if curr_logs else "Empty."
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
                for e in events.items[-10:]:
                    context += f"[{e.reason}] {e.message} (x{e.count or 1})\n"
            except Exception as e:
                context += f"Failed to fetch events: {e}\n"
        
        else:
            context += f"Unsupported resource_type: {resource_type}. Use 'pod' or 'node'."

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
