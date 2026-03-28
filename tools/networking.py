"""Networking tools: Services, Ingresses, Endpoints, NetworkPolicies."""

from kubernetes import client


def register(mcp):
    """Register all networking tools on the MCP server."""
    v1 = client.CoreV1Api()
    networking_v1 = client.NetworkingV1Api()

    @mcp.tool()
    def list_services(namespace: str = "default") -> str:
        """List Services in a namespace with type, ClusterIP, external IP, and ports."""
        try:
            svcs = v1.list_namespaced_service(namespace=namespace)
            if not svcs.items:
                return f"No Services in namespace '{namespace}'."
            lines = []
            for s in svcs.items:
                name = s.metadata.name
                svc_type = s.spec.type
                cluster_ip = s.spec.cluster_ip or "<none>"
                external = "<none>"
                if s.status.load_balancer and s.status.load_balancer.ingress:
                    external = s.status.load_balancer.ingress[0].ip or s.status.load_balancer.ingress[0].hostname or "<pending>"
                ports_str = ", ".join(
                    f"{p.port}{'->' + str(p.node_port) if p.node_port else ''}/{p.protocol}"
                    for p in (s.spec.ports or [])
                )
                lines.append(
                    f"  {name}  |  Type: {svc_type}  |  ClusterIP: {cluster_ip}  "
                    f"|  External: {external}  |  Ports: {ports_str}"
                )
            return f"SERVICES in '{namespace}' ({len(svcs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing services: {e}"

    @mcp.tool()
    def describe_service(name: str, namespace: str = "default") -> str:
        """Get detailed info about a Service: selector, endpoints, ports."""
        try:
            s = v1.read_namespaced_service(name=name, namespace=namespace)
            lines = [
                f"SERVICE: {s.metadata.name}  (namespace: {namespace})",
                f"  Type: {s.spec.type}  |  ClusterIP: {s.spec.cluster_ip}",
                f"  Selector: {s.spec.selector}",
                f"  Session Affinity: {s.spec.session_affinity}",
                "",
                "  PORTS:",
            ]
            for p in s.spec.ports or []:
                lines.append(
                    f"    {p.name or '<unnamed>'}  |  {p.port} -> {p.target_port}  "
                    f"|  NodePort: {p.node_port or 'N/A'}  |  Protocol: {p.protocol}"
                )

            # Endpoints
            try:
                ep = v1.read_namespaced_endpoints(name=name, namespace=namespace)
                lines.append("")
                lines.append("  ENDPOINTS:")
                for subset in ep.subsets or []:
                    addresses = [a.ip for a in (subset.addresses or [])]
                    not_ready_addrs = [a.ip for a in (subset.not_ready_addresses or [])]
                    lines.append(f"    Ready: {', '.join(addresses) or '<none>'}")
                    if not_ready_addrs:
                        lines.append(f"    NotReady: {', '.join(not_ready_addrs)}")
            except Exception:
                lines.append("  ENDPOINTS: <unable to fetch>")

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing service '{name}': {e}"

    @mcp.tool()
    def list_ingresses(namespace: str = "default") -> str:
        """List Ingresses in a namespace with hosts, paths, and backends."""
        try:
            ings = networking_v1.list_namespaced_ingress(namespace=namespace)
            if not ings.items:
                return f"No Ingresses in namespace '{namespace}'."
            lines = []
            for ing in ings.items:
                name = ing.metadata.name
                cls = ing.spec.ingress_class_name or "<default>"
                rules = []
                for rule in ing.spec.rules or []:
                    host = rule.host or "*"
                    for path in (rule.http.paths if rule.http else []):
                        backend_svc = path.backend.service.name if path.backend.service else "?"
                        backend_port = ""
                        if path.backend.service and path.backend.service.port:
                            backend_port = path.backend.service.port.number or path.backend.service.port.name
                        rules.append(f"{host}{path.path} -> {backend_svc}:{backend_port}")
                lines.append(f"  {name}  |  Class: {cls}  |  Rules: {'; '.join(rules) or '<none>'}")
            return f"INGRESSES in '{namespace}' ({len(ings.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing ingresses: {e}"

    @mcp.tool()
    def list_network_policies(namespace: str = "default") -> str:
        """List NetworkPolicies in a namespace with pod selector and policy types."""
        try:
            nps = networking_v1.list_namespaced_network_policy(namespace=namespace)
            if not nps.items:
                return f"No NetworkPolicies in namespace '{namespace}'."
            lines = []
            for np in nps.items:
                name = np.metadata.name
                selector = np.spec.pod_selector.match_labels if np.spec.pod_selector else {}
                policy_types = np.spec.policy_types or []
                ingress_rules = len(np.spec.ingress or [])
                egress_rules = len(np.spec.egress or [])
                lines.append(
                    f"  {name}  |  Selector: {selector}  |  Types: {','.join(policy_types)}  "
                    f"|  Ingress rules: {ingress_rules}  |  Egress rules: {egress_rules}"
                )
            return f"NETWORK POLICIES in '{namespace}' ({len(nps.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing network policies: {e}"

    @mcp.tool()
    def list_endpoints(namespace: str = "default") -> str:
        """List Endpoints in a namespace showing ready/not-ready addresses and ports."""
        try:
            eps = v1.list_namespaced_endpoints(namespace=namespace)
            if not eps.items:
                return f"No Endpoints in namespace '{namespace}'."
            lines = []
            for ep in eps.items:
                name = ep.metadata.name
                total_ready = 0
                total_not_ready = 0
                for subset in ep.subsets or []:
                    total_ready += len(subset.addresses or [])
                    total_not_ready += len(subset.not_ready_addresses or [])
                lines.append(f"  {name}  |  Ready: {total_ready}  |  NotReady: {total_not_ready}")
            return f"ENDPOINTS in '{namespace}' ({len(eps.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing endpoints: {e}"
