"""Workload management tools: Deployments, StatefulSets, DaemonSets, Jobs, CronJobs."""

from kubernetes import client


def register(mcp):
    """Register all workload tools on the MCP server."""
    apps_v1 = client.AppsV1Api()
    batch_v1 = client.BatchV1Api()

    @mcp.tool()
    def list_deployments(namespace: str = "default") -> str:
        """List Deployments in a namespace with replicas, ready, available, and age."""
        try:
            deps = apps_v1.list_namespaced_deployment(namespace=namespace)
            if not deps.items:
                return f"No Deployments found in namespace '{namespace}'."
            lines = []
            for d in deps.items:
                name = d.metadata.name
                desired = d.spec.replicas or 0
                ready = d.status.ready_replicas or 0
                available = d.status.available_replicas or 0
                updated = d.status.updated_replicas or 0
                age = _age(d.metadata.creation_timestamp)
                lines.append(
                    f"  {name}  |  {ready}/{desired} ready  |  {available} available  "
                    f"|  {updated} updated  |  Age: {age}"
                )
            return f"DEPLOYMENTS in '{namespace}' ({len(deps.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing deployments: {e}"

    @mcp.tool()
    def describe_deployment(name: str, namespace: str = "default") -> str:
        """Get detailed info about a Deployment: strategy, conditions, pod template, labels."""
        try:
            d = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            strategy = d.spec.strategy.type if d.spec.strategy else "N/A"
            lines = [
                f"DEPLOYMENT: {d.metadata.name}  (namespace: {namespace})",
                f"  Replicas: {d.spec.replicas}  |  Strategy: {strategy}",
                f"  Selector: {d.spec.selector.match_labels}",
                "",
                "  CONDITIONS:",
            ]
            for c in d.status.conditions or []:
                lines.append(f"    {c.type}: {c.status} — {c.reason}: {c.message or ''}")

            lines.append("")
            lines.append("  CONTAINERS:")
            for c in d.spec.template.spec.containers:
                res = c.resources
                limits = dict(res.limits) if res and res.limits else {}
                requests = dict(res.requests) if res and res.requests else {}
                lines.append(f"    {c.name}  |  Image: {c.image}")
                lines.append(f"      Requests: {requests}  |  Limits: {limits}")
                if c.ports:
                    ports = ", ".join(str(p.container_port) for p in c.ports)
                    lines.append(f"      Ports: {ports}")

            labels = d.metadata.labels or {}
            lines.append("")
            lines.append(f"  LABELS: {labels}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error describing deployment '{name}': {e}"

    @mcp.tool()
    def list_statefulsets(namespace: str = "default") -> str:
        """List StatefulSets in a namespace with ready/desired replicas."""
        try:
            sts_list = apps_v1.list_namespaced_stateful_set(namespace=namespace)
            if not sts_list.items:
                return f"No StatefulSets in namespace '{namespace}'."
            lines = []
            for s in sts_list.items:
                ready = s.status.ready_replicas or 0
                desired = s.spec.replicas or 0
                lines.append(f"  {s.metadata.name}  |  {ready}/{desired} ready  |  Age: {_age(s.metadata.creation_timestamp)}")
            return f"STATEFULSETS in '{namespace}' ({len(sts_list.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing statefulsets: {e}"

    @mcp.tool()
    def list_daemonsets(namespace: str = "default") -> str:
        """List DaemonSets in a namespace with desired/ready/available."""
        try:
            ds_list = apps_v1.list_namespaced_daemon_set(namespace=namespace)
            if not ds_list.items:
                return f"No DaemonSets in namespace '{namespace}'."
            lines = []
            for d in ds_list.items:
                desired = d.status.desired_number_scheduled or 0
                ready = d.status.number_ready or 0
                available = d.status.number_available or 0
                lines.append(
                    f"  {d.metadata.name}  |  Desired: {desired}  |  Ready: {ready}  "
                    f"|  Available: {available}  |  Age: {_age(d.metadata.creation_timestamp)}"
                )
            return f"DAEMONSETS in '{namespace}' ({len(ds_list.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing daemonsets: {e}"

    @mcp.tool()
    def list_jobs(namespace: str = "default") -> str:
        """List Jobs in a namespace with status, completions, and duration."""
        try:
            jobs = batch_v1.list_namespaced_job(namespace=namespace)
            if not jobs.items:
                return f"No Jobs in namespace '{namespace}'."
            lines = []
            for j in jobs.items:
                name = j.metadata.name
                succeeded = j.status.succeeded or 0
                failed = j.status.failed or 0
                completions = j.spec.completions or 1
                active = j.status.active or 0
                lines.append(
                    f"  {name}  |  Succeeded: {succeeded}/{completions}  "
                    f"|  Failed: {failed}  |  Active: {active}  |  Age: {_age(j.metadata.creation_timestamp)}"
                )
            return f"JOBS in '{namespace}' ({len(jobs.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing jobs: {e}"

    @mcp.tool()
    def list_cronjobs(namespace: str = "default") -> str:
        """List CronJobs in a namespace with schedule, last schedule time, and active count."""
        try:
            cj_list = batch_v1.list_namespaced_cron_job(namespace=namespace)
            if not cj_list.items:
                return f"No CronJobs in namespace '{namespace}'."
            lines = []
            for cj in cj_list.items:
                name = cj.metadata.name
                schedule = cj.spec.schedule
                suspend = cj.spec.suspend
                last = cj.status.last_schedule_time or "Never"
                active = len(cj.status.active or [])
                lines.append(
                    f"  {name}  |  Schedule: {schedule}  |  Suspended: {suspend}  "
                    f"|  Last Run: {last}  |  Active: {active}"
                )
            return f"CRONJOBS in '{namespace}' ({len(cj_list.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing cronjobs: {e}"

    @mcp.tool()
    def describe_job(name: str, namespace: str = "default") -> str:
        """Get detailed information about a specific Job."""
        try:
            j = batch_v1.read_namespaced_job(name=name, namespace=namespace)
            lines = [
                f"JOB: {j.metadata.name}  (namespace: {namespace})",
                f"  Completions: {j.spec.completions}  |  Parallelism: {j.spec.parallelism}",
                f"  BackoffLimit: {j.spec.backoff_limit}",
                f"  Succeeded: {j.status.succeeded or 0}  |  Failed: {j.status.failed or 0}  |  Active: {j.status.active or 0}",
                f"  Start: {j.status.start_time}  |  Completion: {j.status.completion_time or 'N/A'}",
            ]
            if j.status.conditions:
                lines.append("  CONDITIONS:")
                for c in j.status.conditions:
                    lines.append(f"    {c.type}: {c.status} — {c.reason}")
            # Pod template
            lines.append("  CONTAINERS:")
            for c in j.spec.template.spec.containers:
                lines.append(f"    {c.name}  |  Image: {c.image}")
                if c.command:
                    lines.append(f"      Command: {' '.join(c.command)}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error describing job '{name}': {e}"

    @mcp.tool()
    def list_replicasets(namespace: str = "default") -> str:
        """List ReplicaSets in a namespace with desired/ready replicas and owner."""
        try:
            rs_list = apps_v1.list_namespaced_replica_set(namespace=namespace)
            if not rs_list.items:
                return f"No ReplicaSets in namespace '{namespace}'."
            lines = []
            for rs in rs_list.items:
                desired = rs.spec.replicas or 0
                ready = rs.status.ready_replicas or 0
                owner = ""
                if rs.metadata.owner_references:
                    o = rs.metadata.owner_references[0]
                    owner = f"{o.kind}/{o.name}"
                lines.append(
                    f"  {rs.metadata.name}  |  {ready}/{desired} ready  "
                    f"|  Owner: {owner or '<none>'}  |  Age: {_age(rs.metadata.creation_timestamp)}"
                )
            return f"REPLICASETS in '{namespace}' ({len(rs_list.items)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing replicasets: {e}"


def _age(creation_timestamp) -> str:
    """Compute a human-readable age from creation timestamp."""
    if not creation_timestamp:
        return "Unknown"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    delta = now - creation_timestamp.replace(tzinfo=timezone.utc) if creation_timestamp.tzinfo is None else now - creation_timestamp
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{total_seconds // 60}m"
    elif total_seconds < 86400:
        return f"{total_seconds // 3600}h"
    else:
        return f"{total_seconds // 86400}d"
