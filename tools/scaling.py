"""Scaling and autoscaling tools: HPAs, manual scaling of Deployments and StatefulSets."""

from kubernetes import client


def register(mcp):
    autoscaling_v1 = client.AutoscalingV1Api()
    apps_v1 = client.AppsV1Api()
    @mcp.tool()
    def list_hpas(namespace: str = "default") -> str:
        """List HorizontalPodAutoscalers in a namespace with min/max/current replicas and target CPU."""
        try:
            hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace=namespace)
            if not hpas.items:
                return f"No HPAs in namespace '{namespace}'."
            lines = []
            for h in hpas.items:
                name = h.metadata.name
                ref = f"{h.spec.scale_target_ref.kind}/{h.spec.scale_target_ref.name}"
                min_r = h.spec.min_replicas or 1
                max_r = h.spec.max_replicas
                current = h.status.current_replicas or 0
                target_cpu = h.spec.target_cpu_utilization_percentage or "N/A"
                current_cpu = h.status.current_cpu_utilization_percentage
                cpu_display = f"{current_cpu}%" if current_cpu is not None else "?"
                lines.append(
                    f"  {name}  |  Target: {ref}  |  Replicas: {current} ({min_r}-{max_r})  "
                    f"|  CPU Target: {target_cpu}%  |  CPU Current: {cpu_display}"
                )
            return f"HPAs in '{namespace}' ({len(hpas.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing HPAs: {e}"

    @mcp.tool()
    def scale_deployment(name: str, namespace: str, replicas: int) -> str:
        """Manually scale a Deployment to the specified number of replicas."""
        try:
            if replicas < 0:
                return "Error: replicas must be >= 0."
            body = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
            return f"✅ Deployment '{name}' in '{namespace}' scaled to {replicas} replicas."
        except Exception as e:
            return f"❌ Error scaling deployment '{name}': {e}"

    @mcp.tool()
    def scale_statefulset(name: str, namespace: str, replicas: int) -> str:
        """Manually scale a StatefulSet to the specified number of replicas."""
        try:
            if replicas < 0:
                return "Error: replicas must be >= 0."
            body = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_stateful_set_scale(name=name, namespace=namespace, body=body)
            return f"✅ StatefulSet '{name}' in '{namespace}' scaled to {replicas} replicas."
        except Exception as e:
            return f"❌ Error scaling statefulset '{name}': {e}"
