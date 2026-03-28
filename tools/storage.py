"""Storage tools: PersistentVolumes, PersistentVolumeClaims, StorageClasses."""

from kubernetes import client


def register(mcp):
    """Register all storage tools on the MCP server."""
    v1 = client.CoreV1Api()
    storage_v1 = client.StorageV1Api()

    @mcp.tool()
    def list_pvs() -> str:
        """List all PersistentVolumes with capacity, access modes, reclaim policy, status, and bound claim."""
        try:
            pvs = v1.list_persistent_volume()
            if not pvs.items:
                return "No PersistentVolumes found in the cluster."
            lines = []
            for pv in pvs.items:
                name = pv.metadata.name
                capacity = pv.spec.capacity.get("storage", "?") if pv.spec.capacity else "?"
                access = ",".join(pv.spec.access_modes or [])
                reclaim = pv.spec.persistent_volume_reclaim_policy or "?"
                status = pv.status.phase
                claim = ""
                if pv.spec.claim_ref:
                    claim = f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"
                sc = pv.spec.storage_class_name or "<none>"
                lines.append(
                    f"  {name}  |  Capacity: {capacity}  |  Access: {access}  "
                    f"|  Reclaim: {reclaim}  |  Status: {status}  |  Claim: {claim or '<none>'}  |  SC: {sc}"
                )
            return f"PERSISTENT VOLUMES ({len(pvs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing PVs: {e}"

    @mcp.tool()
    def list_pvcs(namespace: str = "default") -> str:
        """List PersistentVolumeClaims in a namespace with status, capacity, access modes, and bound PV."""
        try:
            pvcs = v1.list_namespaced_persistent_volume_claim(namespace=namespace)
            if not pvcs.items:
                return f"No PVCs in namespace '{namespace}'."
            lines = []
            for pvc in pvcs.items:
                name = pvc.metadata.name
                status = pvc.status.phase
                capacity = "?"
                if pvc.status.capacity:
                    capacity = pvc.status.capacity.get("storage", "?")
                access = ",".join(pvc.spec.access_modes or [])
                volume = pvc.spec.volume_name or "<pending>"
                sc = pvc.spec.storage_class_name or "<default>"
                lines.append(
                    f"  {name}  |  Status: {status}  |  Capacity: {capacity}  "
                    f"|  Access: {access}  |  Volume: {volume}  |  SC: {sc}"
                )
            return f"PVCs in '{namespace}' ({len(pvcs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing PVCs: {e}"

    @mcp.tool()
    def describe_pvc(name: str, namespace: str = "default") -> str:
        """Get detailed info about a PVC including conditions and events."""
        try:
            pvc = v1.read_namespaced_persistent_volume_claim(name=name, namespace=namespace)
            lines = [
                f"PVC: {pvc.metadata.name}  (namespace: {namespace})",
                f"  Status: {pvc.status.phase}",
                f"  Volume: {pvc.spec.volume_name or '<pending>'}",
                f"  StorageClass: {pvc.spec.storage_class_name or '<default>'}",
                f"  Access Modes: {pvc.spec.access_modes}",
                f"  Capacity: {pvc.status.capacity.get('storage', '?') if pvc.status.capacity else '?'}",
                f"  Requested: {pvc.spec.resources.requests.get('storage', '?') if pvc.spec.resources and pvc.spec.resources.requests else '?'}",
            ]

            # Conditions
            if pvc.status.conditions:
                lines.append("")
                lines.append("  CONDITIONS:")
                for c in pvc.status.conditions:
                    lines.append(f"    {c.type}: {c.status} — {c.message or ''}")

            # Events
            lines.append("")
            lines.append("  EVENTS:")
            events = v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={name},involvedObject.kind=PersistentVolumeClaim"
            )
            for ev in (events.items or [])[-5:]:
                lines.append(f"    [{ev.type}] {ev.reason}: {ev.message}")
            if not events.items:
                lines.append("    <no events>")

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing PVC '{name}': {e}"

    @mcp.tool()
    def list_storage_classes() -> str:
        """List StorageClasses with provisioner, reclaim policy, volume binding mode, and parameters."""
        try:
            scs = storage_v1.list_storage_class()
            if not scs.items:
                return "No StorageClasses found in the cluster."
            lines = []
            for sc in scs.items:
                name = sc.metadata.name
                provisioner = sc.provisioner
                reclaim = sc.reclaim_policy or "Delete"
                bind_mode = sc.volume_binding_mode or "Immediate"
                is_default = "kubernetes.io/is-default-class" in (sc.metadata.annotations or {})
                params = sc.parameters or {}
                params_str = ", ".join(f"{k}={v}" for k, v in params.items()) or "<none>"
                lines.append(
                    f"  {name}{'  (default)' if is_default else ''}  |  Provisioner: {provisioner}  "
                    f"|  Reclaim: {reclaim}  |  Binding: {bind_mode}  |  Params: {params_str}"
                )
            return f"STORAGE CLASSES ({len(scs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing storage classes: {e}"
