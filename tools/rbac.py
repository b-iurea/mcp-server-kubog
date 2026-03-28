"""RBAC tools: Roles, ClusterRoles, RoleBindings, ClusterRoleBindings, ServiceAccounts."""

from kubernetes import client


def register(mcp):
    """Register all RBAC tools on the MCP server."""
    v1 = client.CoreV1Api()
    rbac_v1 = client.RbacAuthorizationV1Api()

    @mcp.tool()
    def list_service_accounts(namespace: str = "default") -> str:
        """List ServiceAccounts in a namespace with secrets count."""
        try:
            sas = v1.list_namespaced_service_account(namespace=namespace)
            if not sas.items:
                return f"No ServiceAccounts in namespace '{namespace}'."
            lines = []
            for sa in sas.items:
                name = sa.metadata.name
                secrets_count = len(sa.secrets or [])
                age = _age(sa.metadata.creation_timestamp)
                lines.append(f"  {name}  |  Secrets: {secrets_count}  |  Age: {age}")
            return f"SERVICE ACCOUNTS in '{namespace}' ({len(sas.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing service accounts: {e}"

    @mcp.tool()
    def list_roles(namespace: str = "default") -> str:
        """List Roles in a namespace with number of rules."""
        try:
            roles = rbac_v1.list_namespaced_role(namespace=namespace)
            if not roles.items:
                return f"No Roles in namespace '{namespace}'."
            lines = []
            for r in roles.items:
                name = r.metadata.name
                rules_count = len(r.rules or [])
                lines.append(f"  {name}  |  Rules: {rules_count}  |  Age: {_age(r.metadata.creation_timestamp)}")
            return f"ROLES in '{namespace}' ({len(roles.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing roles: {e}"

    @mcp.tool()
    def list_cluster_roles() -> str:
        """List ClusterRoles with number of rules. Shows first 30 results to avoid excessive output."""
        try:
            roles = rbac_v1.list_cluster_role()
            if not roles.items:
                return "No ClusterRoles found."
            lines = []
            for r in roles.items[:30]:
                name = r.metadata.name
                rules_count = len(r.rules or [])
                lines.append(f"  {name}  |  Rules: {rules_count}")
            total = len(roles.items)
            shown = min(total, 30)
            footer = f"  ... showing {shown}/{total}" if total > 30 else ""
            return f"CLUSTER ROLES ({total}):\n" + "\n".join(lines) + ("\n" + footer if footer else "")
        except Exception as e:
            return f"Error listing cluster roles: {e}"

    @mcp.tool()
    def list_role_bindings(namespace: str = "default") -> str:
        """List RoleBindings in a namespace with subjects and referenced role."""
        try:
            rbs = rbac_v1.list_namespaced_role_binding(namespace=namespace)
            if not rbs.items:
                return f"No RoleBindings in namespace '{namespace}'."
            lines = []
            for rb in rbs.items:
                name = rb.metadata.name
                role_ref = f"{rb.role_ref.kind}/{rb.role_ref.name}"
                subjects = ", ".join(
                    f"{s.kind}:{s.name}" for s in (rb.subjects or [])
                ) or "<none>"
                lines.append(f"  {name}  |  Role: {role_ref}  |  Subjects: {subjects}")
            return f"ROLE BINDINGS in '{namespace}' ({len(rbs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing role bindings: {e}"

    @mcp.tool()
    def list_cluster_role_bindings() -> str:
        """List ClusterRoleBindings with subjects and referenced role. Shows first 30 results."""
        try:
            crbs = rbac_v1.list_cluster_role_binding()
            if not crbs.items:
                return "No ClusterRoleBindings found."
            lines = []
            for crb in crbs.items[:30]:
                name = crb.metadata.name
                role_ref = f"{crb.role_ref.kind}/{crb.role_ref.name}"
                subjects = ", ".join(
                    f"{s.kind}:{s.name}" for s in (crb.subjects or [])
                ) or "<none>"
                lines.append(f"  {name}  |  Role: {role_ref}  |  Subjects: {subjects}")
            total = len(crbs.items)
            shown = min(total, 30)
            footer = f"  ... showing {shown}/{total}" if total > 30 else ""
            return f"CLUSTER ROLE BINDINGS ({total}):\n" + "\n".join(lines) + ("\n" + footer if footer else "")
        except Exception as e:
            return f"Error listing cluster role bindings: {e}"


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
