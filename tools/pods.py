"""Pod operations tools: list, describe, logs, resource usage."""

from kubernetes import client


def register(mcp):
    """Register all pod tools on the MCP server."""
    v1 = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    @mcp.tool()
    def list_pods(namespace: str = "default", label_selector: str = "") -> str:
        """List pods in a namespace with status, restarts, age, node, and IP. Optionally filter by label selector (e.g. 'app=nginx')."""
        try:
            kwargs = {"namespace": namespace}
            if label_selector:
                kwargs["label_selector"] = label_selector
            pods = v1.list_namespaced_pod(**kwargs)
            if not pods.items:
                return f"No pods found in namespace '{namespace}'."
            lines = []
            for p in pods.items:
                name = p.metadata.name
                phase = p.status.phase
                node = p.spec.node_name or "<pending>"
                ip = p.status.pod_ip or "<none>"
                restarts = 0
                for cs in p.status.container_statuses or []:
                    restarts += cs.restart_count
                age = _age(p.metadata.creation_timestamp)
                lines.append(
                    f"  {name}  |  Status: {phase}  |  Restarts: {restarts}  "
                    f"|  Node: {node}  |  IP: {ip}  |  Age: {age}"
                )
            return f"PODS in '{namespace}' ({len(pods.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing pods: {e}"

    @mcp.tool()
    def describe_pod(pod_name: str, namespace: str = "default") -> str:
        """Get full detail of a pod: conditions, containers (with state/resources), volumes, events."""
        try:
            p = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            lines = [
                f"POD: {p.metadata.name}  (namespace: {namespace})",
                f"  Node: {p.spec.node_name}  |  Status: {p.status.phase}  |  IP: {p.status.pod_ip}",
                f"  Service Account: {p.spec.service_account_name}",
                "",
                "  CONDITIONS:",
            ]
            for c in p.status.conditions or []:
                lines.append(f"    {c.type}: {c.status}")

            lines.append("")
            lines.append("  CONTAINERS:")
            for c in p.spec.containers:
                lines.append(f"    {c.name}  |  Image: {c.image}")
                res = c.resources
                if res:
                    req = dict(res.requests) if res.requests else {}
                    lim = dict(res.limits) if res.limits else {}
                    lines.append(f"      Requests: {req}  |  Limits: {lim}")
                if c.ports:
                    ports_str = ", ".join(f"{cp.container_port}/{cp.protocol}" for cp in c.ports)
                    lines.append(f"      Ports: {ports_str}")

            # Container statuses
            lines.append("")
            lines.append("  CONTAINER STATUSES:")
            for cs in p.status.container_statuses or []:
                state_key = "running" if cs.state.running else ("waiting" if cs.state.waiting else "terminated")
                state_detail = ""
                if cs.state.waiting:
                    state_detail = f" ({cs.state.waiting.reason})"
                elif cs.state.terminated:
                    state_detail = f" (reason={cs.state.terminated.reason}, exitCode={cs.state.terminated.exit_code})"
                lines.append(
                    f"    {cs.name}  |  Ready: {cs.ready}  |  State: {state_key}{state_detail}  "
                    f"|  Restarts: {cs.restart_count}"
                )

            # Volumes
            if p.spec.volumes:
                lines.append("")
                lines.append(f"  VOLUMES ({len(p.spec.volumes)}):")
                for vol in p.spec.volumes[:10]:  # Limit to first 10
                    vol_type = _get_volume_type(vol)
                    lines.append(f"    {vol.name}  |  Type: {vol_type}")

            # Recent events
            lines.append("")
            lines.append("  RECENT EVENTS:")
            events = v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod"
            )
            for ev in (events.items or [])[-5:]:
                lines.append(f"    [{ev.type}] {ev.reason}: {ev.message}")
            if not events.items:
                lines.append("    <no events>")

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing pod '{pod_name}': {e}"

    @mcp.tool()
    def get_pod_logs(pod_name: str, namespace: str, container: str = "", tail_lines: int = 50, previous: bool = False) -> str:
        """Retrieve logs from a pod. Optionally specify container name, number of tail lines, or previous=True for crash logs."""
        try:
            kwargs = {
                "name": pod_name,
                "namespace": namespace,
                "tail_lines": tail_lines,
                "previous": previous,
            }
            if container:
                kwargs["container"] = container
            logs = v1.read_namespaced_pod_log(**kwargs)
            label = f"(container={container}) " if container else ""
            return f"Logs for {pod_name} {label}(previous={previous}, tail={tail_lines}):\n{logs}"
        except Exception as e:
            return f"Error reading logs: {e}"

    @mcp.tool()
    def get_pod_resource_usage(namespace: str = "default") -> str:
        """Get CPU and memory usage for pods via the Metrics API (requires metrics-server)."""
        try:
            metrics = custom_api.list_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
            )
            lines = []
            for item in metrics.get("items", []):
                pod_name = item["metadata"]["name"]
                for c in item.get("containers", []):
                    cpu = c.get("usage", {}).get("cpu", "?")
                    mem = c.get("usage", {}).get("memory", "?")
                    lines.append(f"  {pod_name}/{c['name']}  |  CPU: {cpu}  |  Memory: {mem}")
            if not lines:
                return f"No pod metrics found in namespace '{namespace}'. Is metrics-server installed?"
            return f"POD RESOURCE USAGE in '{namespace}':\n" + "\n".join(lines)
        except Exception as e:
            return f"Error fetching pod metrics (is metrics-server installed?): {e}"


def _age(creation_timestamp) -> str:
    if not creation_timestamp:
        return "Unknown"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    delta = now - (creation_timestamp.replace(tzinfo=timezone.utc) if creation_timestamp.tzinfo is None else creation_timestamp)
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{total_seconds // 60}m"
    elif total_seconds < 86400:
        return f"{total_seconds // 3600}h"
    else:
        return f"{total_seconds // 86400}d"


def _get_volume_type(vol) -> str:
    """Determine the volume type from a V1Volume object."""
    if vol.config_map:
        return f"ConfigMap({vol.config_map.name})"
    elif vol.secret:
        return f"Secret({vol.secret.secret_name})"
    elif vol.persistent_volume_claim:
        return f"PVC({vol.persistent_volume_claim.claim_name})"
    elif vol.empty_dir is not None:
        return "EmptyDir"
    elif vol.host_path:
        return f"HostPath({vol.host_path.path})"
    elif vol.projected:
        return "Projected"
    elif vol.downward_api:
        return "DownwardAPI"
    else:
        return "Other"
