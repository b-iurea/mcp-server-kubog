"""Custom resource definitions and objects tools."""

import json
from kubernetes import client
from tools.utils import to_compact_yaml

def register(mcp):
    """Register custom resources tools."""
    custom_api = client.CustomObjectsApi()
    
    # Optional: we can load this only if called, but creating it is cheap
    try:
        ext_api = client.ApiextensionsV1Api()
    except Exception:
        ext_api = None

    @mcp.tool()
    def list_crds() -> str:
        """List all Custom Resource Definitions (CRDs) available in the cluster. Useful to discover what 'plurals', 'groups', and 'versions' are available."""
        if not ext_api:
            return "ApiextensionsV1Api is not available. Ensure your client is properly initialized."
        try:
            crds = ext_api.list_custom_resource_definition()
            if not crds.items:
                return "No CRDs found in the cluster."
            
            lines = []
            for crd in crds.items:
                name = crd.metadata.name
                group = crd.spec.group
                scope = crd.spec.scope
                # usually versions is a list, we show the stored versions
                versions = [v.name for v in crd.spec.versions]
                plural = crd.spec.names.plural
                lines.append(f"CRD: {name} | Group: {group} | Plural: {plural} | Versions: {versions} | Scope: {scope}")
            
            return f"CUSTOM RESOURCE DEFINITIONS ({len(crds.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing CRDs: {e}"

    @mcp.tool()
    def list_custom_resources(group: str, version: str, plural: str, namespace: str = None) -> str:
        """
        List Custom Resources for a specific CRD.
        If namespace is provided, lists in that namespace. Otherwise, lists cluster-wide.
        Requires exact 'group', 'version', and 'plural' (e.g., group='cert-manager.io', version='v1', plural='certificates').
        """
        try:
            if namespace:
                objs = custom_api.list_namespaced_custom_object(group=group, version=version, namespace=namespace, plural=plural)
            else:
                objs = custom_api.list_cluster_custom_object(group=group, version=version, plural=plural)
                
            items = objs.get('items', [])
            if not items:
                ns_msg = f"in namespace '{namespace}'" if namespace else "cluster-wide"
                return f"No custom resources of type {plural}.{group}/{version} found {ns_msg}."
                
            lines = []
            for idx, item in enumerate(items):
                meta = item.get('metadata', {})
                name = meta.get('name', 'Unknown')
                ns = meta.get('namespace', 'ClusterWide')
                
                # Try to extract a simple status summary if it exists
                status = item.get('status', {})
                status_summary = ""
                if isinstance(status, dict) and 'conditions' in status:
                    conds = status['conditions']
                    if conds and isinstance(conds, list):
                        latest = conds[-1]
                        status_summary = f" | Status: [{latest.get('type')}] {latest.get('status')}"
                
                lines.append(f"{idx+1}. [{ns}] {name}{status_summary}")
                
            return f"CUSTOM RESOURCES ({group}/{version}/{plural}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing custom resources: {e}"

    @mcp.tool()
    def get_custom_resource(group: str, version: str, plural: str, name: str, namespace: str = None) -> str:
        """
        Get the full representation of a specific Custom Resource.
        If the CRD is namespace-scoped, you must provide the namespace.
        """
        try:
            if namespace:
                obj = custom_api.get_namespaced_custom_object(group=group, version=version, namespace=namespace, plural=plural, name=name)
            else:
                obj = custom_api.get_cluster_custom_object(group=group, version=version, plural=plural, name=name)
            
            # Format nicely as YAML without bloat
            return f"CUSTOM RESOURCE: {name} ({group}/{version}/{plural})\n" + to_compact_yaml(obj)
        except Exception as e:
            return f"Error fetching custom resource: {e}"
