"""Configuration tools: ConfigMaps and Secrets."""

import base64
from kubernetes import client


def register(mcp):
    """Register all config tools on the MCP server."""
    v1 = client.CoreV1Api()

    @mcp.tool()
    def list_configmaps(namespace: str = "default") -> str:
        """List ConfigMaps in a namespace with data keys count and age."""
        try:
            cms = v1.list_namespaced_config_map(namespace=namespace)
            if not cms.items:
                return f"No ConfigMaps in namespace '{namespace}'."
            lines = []
            for cm in cms.items:
                name = cm.metadata.name
                keys_count = len(cm.data or {})
                age = _age(cm.metadata.creation_timestamp)
                lines.append(f"  {name}  |  Keys: {keys_count}  |  Age: {age}")
            return f"CONFIGMAPS in '{namespace}' ({len(cms.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing configmaps: {e}"

    @mcp.tool()
    def get_configmap(name: str, namespace: str = "default") -> str:
        """Get the data (keys and values) of a specific ConfigMap."""
        try:
            cm = v1.read_namespaced_config_map(name=name, namespace=namespace)
            lines = [f"CONFIGMAP: {cm.metadata.name}  (namespace: {namespace})", ""]
            data = cm.data or {}
            if not data:
                lines.append("  <no data>")
            for key, value in data.items():
                # Truncate very long values
                display_value = value if len(value) <= 500 else value[:500] + f"... ({len(value)} chars total)"
                lines.append(f"  --- {key} ---")
                lines.append(f"  {display_value}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading configmap '{name}': {e}"

    @mcp.tool()
    def list_secrets(namespace: str = "default") -> str:
        """List Secrets in a namespace with type, data keys count, and age. Values are NOT shown."""
        try:
            secrets = v1.list_namespaced_secret(namespace=namespace)
            if not secrets.items:
                return f"No Secrets in namespace '{namespace}'."
            lines = []
            for s in secrets.items:
                name = s.metadata.name
                s_type = s.type or "Opaque"
                keys_count = len(s.data or {})
                age = _age(s.metadata.creation_timestamp)
                lines.append(f"  {name}  |  Type: {s_type}  |  Keys: {keys_count}  |  Age: {age}")
            return f"SECRETS in '{namespace}' ({len(secrets.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing secrets: {e}"

    @mcp.tool()
    def describe_secret(name: str, namespace: str = "default", decode: bool = False) -> str:
        """Show keys of a Secret. Set decode=True to also show decoded values (base64). By default only keys and sizes are shown."""
        try:
            s = v1.read_namespaced_secret(name=name, namespace=namespace)
            lines = [
                f"SECRET: {s.metadata.name}  (namespace: {namespace})",
                f"  Type: {s.type}",
                "",
                "  DATA:",
            ]
            data = s.data or {}
            if not data:
                lines.append("    <no data>")
            for key, value in data.items():
                if decode:
                    try:
                        decoded = base64.b64decode(value).decode("utf-8", errors="replace")
                        display = decoded if len(decoded) <= 200 else decoded[:200] + "..."
                        lines.append(f"    {key}: {display}")
                    except Exception:
                        lines.append(f"    {key}: <decode error>")
                else:
                    size = len(base64.b64decode(value)) if value else 0
                    lines.append(f"    {key}  ({size} bytes)")

            return "\n".join(lines)
        except Exception as e:
            return f"Error describing secret '{name}': {e}"


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
