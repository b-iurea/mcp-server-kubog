"""Cluster-level overview tools: nodes, namespaces, resource usage."""

from kubernetes import client


def register(mcp):
    """Register all cluster tools on the MCP server."""
    v1 = client.CoreV1Api()

    @mcp.tool()
    def list_nodes() -> str:
        """List all cluster nodes with status, roles, version, and capacity (CPU/memory)."""
        try:
            nodes = v1.list_node()
            lines = []
            for n in nodes.items:
                name = n.metadata.name
                # Determine roles from labels
                roles = [
                    k.replace("node-role.kubernetes.io/", "")
                    for k in (n.metadata.labels or {})
                    if k.startswith("node-role.kubernetes.io/")
                ] or ["<none>"]
                # Status conditions
                ready = "Unknown"
                for c in n.status.conditions or []:
                    if c.type == "Ready":
                        ready = "Ready" if c.status == "True" else "NotReady"
                version = n.status.node_info.kubelet_version
                cpu = n.status.allocatable.get("cpu", "?")
                mem = n.status.allocatable.get("memory", "?")
                lines.append(
                    f"  {name}  |  Roles: {','.join(roles)}  |  Status: {ready}  "
                    f"|  Version: {version}  |  CPU: {cpu}  |  Memory: {mem}"
                )
            header = f"NODES ({len(nodes.items)}):"
            return header + "\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing nodes: {e}"

    @mcp.tool()
    def describe_node(node_name: str) -> str:
        """Get detailed information about a specific node: conditions, taints, allocatable resources, labels."""
        try:
            n = v1.read_node(name=node_name)
            info = n.status.node_info
            lines = [
                f"NODE: {n.metadata.name}",
                f"  OS: {info.os_image}  |  Kernel: {info.kernel_version}  |  Container Runtime: {info.container_runtime_version}",
                f"  Kubelet: {info.kubelet_version}",
                "",
                "  CONDITIONS:",
            ]
            for c in n.status.conditions or []:
                lines.append(f"    {c.type}: {c.status} — {c.message or 'N/A'}")

            lines.append("")
            lines.append("  ALLOCATABLE RESOURCES:")
            for res, val in (n.status.allocatable or {}).items():
                lines.append(f"    {res}: {val}")

            taints = n.spec.taints or []
            lines.append("")
            lines.append(f"  TAINTS ({len(taints)}):")
            for t in taints:
                lines.append(f"    {t.key}={t.value or ''}:{t.effect}")

            labels = n.metadata.labels or {}
            lines.append("")
            lines.append(f"  LABELS ({len(labels)}):")
            for k, val in sorted(labels.items()):
                lines.append(f"    {k}={val}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing node '{node_name}': {e}"

    @mcp.tool()
    def list_namespaces() -> str:
        """List all namespaces with status and labels."""
        try:
            ns_list = v1.list_namespace()
            lines = []
            for ns in ns_list.items:
                name = ns.metadata.name
                status = ns.status.phase
                labels = ", ".join(f"{k}={v}" for k, v in (ns.metadata.labels or {}).items())
                lines.append(f"  {name}  |  Status: {status}  |  Labels: {labels or '<none>'}")
            header = f"NAMESPACES ({len(ns_list.items)}):"
            return header + "\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing namespaces: {e}"

    @mcp.tool()
    def cluster_resource_usage() -> str:
        """Show aggregate resource requests vs allocatable capacity across all nodes."""
        try:
            nodes = v1.list_node()
            total_cpu_alloc = 0
            total_mem_alloc_mi = 0
            total_cpu_req = 0
            total_mem_req_mi = 0

            # Parse allocatable
            for n in nodes.items:
                cpu_str = n.status.allocatable.get("cpu", "0")
                mem_str = n.status.allocatable.get("memory", "0")
                total_cpu_alloc += _parse_cpu(cpu_str)
                total_mem_alloc_mi += _parse_memory_mi(mem_str)

            # Sum requests from all pods
            all_pods = v1.list_pod_for_all_namespaces()
            for pod in all_pods.items:
                if pod.status.phase not in ("Running", "Pending"):
                    continue
                for c in pod.spec.containers or []:
                    req = (c.resources.requests or {}) if c.resources else {}
                    total_cpu_req += _parse_cpu(req.get("cpu", "0"))
                    total_mem_req_mi += _parse_memory_mi(req.get("memory", "0"))

            cpu_pct = (total_cpu_req / total_cpu_alloc * 100) if total_cpu_alloc else 0
            mem_pct = (total_mem_req_mi / total_mem_alloc_mi * 100) if total_mem_alloc_mi else 0

            return (
                f"CLUSTER RESOURCE USAGE:\n"
                f"  CPU:    {total_cpu_req:.1f}m requested / {total_cpu_alloc:.1f}m allocatable ({cpu_pct:.1f}%)\n"
                f"  Memory: {total_mem_req_mi:.0f}Mi requested / {total_mem_alloc_mi:.0f}Mi allocatable ({mem_pct:.1f}%)"
            )
        except Exception as e:
            return f"Error computing cluster resource usage: {e}"


def _parse_cpu(val: str) -> float:
    """Parse a CPU string like '500m' or '2' into millicores."""
    val = str(val)
    if val.endswith("m"):
        return float(val[:-1])
    return float(val) * 1000


def _parse_memory_mi(val: str) -> float:
    """Parse a memory string like '1Gi', '512Mi', '1048576Ki' into MiB."""
    val = str(val)
    if val.endswith("Gi"):
        return float(val[:-2]) * 1024
    elif val.endswith("Mi"):
        return float(val[:-2])
    elif val.endswith("Ki"):
        return float(val[:-2]) / 1024
    elif val.endswith("G"):
        return float(val[:-1]) * 1000 / 1.048576
    elif val.endswith("M"):
        return float(val[:-1]) * 1000000 / 1048576
    else:
        # Assume bytes
        try:
            return float(val) / (1024 * 1024)
        except ValueError:
            return 0
