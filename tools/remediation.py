"""Remediation tools: fix OOM, restart, rollback, cordon/uncordon, drain."""

import datetime
from kubernetes import client


def register(mcp, cluster_alerts: dict):
    """Register remediation tools. Receives shared cluster_alerts dict from KOPF."""
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()

    @mcp.tool()
    def fix_oom_resources(pod_name: str, namespace: str, new_memory_limit: str) -> str:
        """Patch the memory limits on the owning Deployment of a given pod. Useful after memory-related crashes. Format: '256Mi', '1Gi'."""
        try:
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            owner = pod.metadata.owner_references[0]

            deployment_name = None
            if owner.kind == "ReplicaSet":
                rs = apps_v1.read_namespaced_replica_set(name=owner.name, namespace=namespace)
                deployment_name = rs.metadata.owner_references[0].name
            elif owner.kind == "Deployment":
                deployment_name = owner.name
            else:
                return f"Cannot patch: pod is managed by {owner.kind}, not a Deployment."

            # Patch all containers
            dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            containers_patch = []
            for c in dep.spec.template.spec.containers:
                containers_patch.append({
                    "name": c.name,
                    "resources": {
                        "limits": {"memory": new_memory_limit},
                        "requests": {"memory": new_memory_limit},
                    }
                })

            patch = {"spec": {"template": {"spec": {"containers": containers_patch}}}}
            apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)
            cluster_alerts.pop(f"{namespace}/{pod_name}", None)
            return f"✅ Deployment '{deployment_name}' memory updated to {new_memory_limit} for all containers."
        except Exception as e:
            return f"❌ Error patching resources: {e}"

    @mcp.tool()
    def restart_deployment(deployment_name: str, namespace: str) -> str:
        """Execute a rollout restart of a Deployment (useful for stuck apps)."""
        try:
            patch = {
                "spec": {"template": {"metadata": {"annotations": {
                    "sre.ai/restartedAt": datetime.datetime.utcnow().isoformat()
                }}}}
            }
            apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)
            return f"✅ Rollout restart initiated for deployment '{deployment_name}'."
        except Exception as e:
            return f"❌ Error during restart: {e}"

    @mcp.tool()
    def rollback_deployment(deployment_name: str, namespace: str) -> str:
        """Rollback a Deployment to its previous revision by scaling down current RS and scaling up previous."""
        try:
            rs_list = apps_v1.list_namespaced_replica_set(
                namespace=namespace,
                label_selector=",".join(f"{k}={v}" for k, v in
                    (apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
                     .spec.selector.match_labels or {}).items())
            )
            if len(rs_list.items) < 2:
                return "Cannot rollback: less than 2 ReplicaSets found. No previous revision available."

            sorted_rs = sorted(rs_list.items,
                key=lambda r: int(r.metadata.annotations.get("deployment.kubernetes.io/revision", "0")),
                reverse=True)

            previous_rs = sorted_rs[1]
            prev_template = previous_rs.spec.template

            patch = {"spec": {"template": prev_template.to_dict()}}
            apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)
            return f"✅ Deployment '{deployment_name}' rolled back to revision with RS '{previous_rs.metadata.name}'."
        except Exception as e:
            return f"❌ Error during rollback: {e}"

    @mcp.tool()
    def cordon_node(node_name: str) -> str:
        """Cordon a node (mark as unschedulable). No new pods will be scheduled on it."""
        try:
            patch = {"spec": {"unschedulable": True}}
            v1.patch_node(name=node_name, body=patch)
            return f"✅ Node '{node_name}' cordoned (unschedulable=True)."
        except Exception as e:
            return f"❌ Error cordoning node: {e}"

    @mcp.tool()
    def uncordon_node(node_name: str) -> str:
        """Uncordon a node (mark as schedulable again)."""
        try:
            patch = {"spec": {"unschedulable": False}}
            v1.patch_node(name=node_name, body=patch)
            return f"✅ Node '{node_name}' uncordoned (unschedulable=False)."
        except Exception as e:
            return f"❌ Error uncordoning node: {e}"
