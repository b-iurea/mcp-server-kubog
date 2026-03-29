import asyncio
import os
import sys
import logging
import threading
import kopf
from mcp.server.fastmcp import FastMCP
from kubernetes import client, config

# Tools modules
from tools import cluster, workloads, pods, networking, storage
from tools import rbac, scaling, diagnostics, remediation
from tools import custom_resources
from tools import config as config_tools  # avoid clash with kubernetes.config

# ==========================================================================
# LOGGING — ALL output MUST go to stderr (stdout = MCP stdio transport)
# ==========================================================================
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

# Override the root logger so nothing ever defaults to stdout
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(stderr_handler)
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("sre-mcp-server")

# Force ALL KOPF-related loggers to stderr + WARNING level.
# KOPF re-configures its own loggers when kopf.operator() starts,
# so we also suppress them inside the startup handler below.
_KOPF_LOGGER_NAMES = (
    "kopf", "kopf._cogs", "kopf._core", "kopf.objects",
    "kopf.activities", "kopf.engines", "kopf.registries",
)
for _name in _KOPF_LOGGER_NAMES:
    _kl = logging.getLogger(_name)
    _kl.handlers.clear()
    _kl.addHandler(stderr_handler)
    _kl.propagate = False
    _kl.setLevel(logging.WARNING)

# ==========================================================================
# MCP SERVER
# ==========================================================================
mcp = FastMCP("K8s-SRE-Operator")

# ==========================================================================
# KUBERNETES CONFIG
# ==========================================================================
try:
    config.load_kube_config(context="workercluster")
    logger.info("Loaded local kubeconfig.")
except config.ConfigException:
    config.load_incluster_config()
    logger.info("Loaded in-cluster config.")

# ==========================================================================
# SHARED STATE — crash alerts detected by KOPF
# ==========================================================================
cluster_alerts = {}

# ==========================================================================
# KOPF BACKGROUND MONITOR
# ==========================================================================

@kopf.on.startup()
def configure_kopf(settings: kopf.OperatorSettings, **_):
    """Configure KOPF to be completely silent on stdout."""
    # Disable KOPF's Kubernetes event posting (it creates Event objects in the cluster)
    settings.posting.enabled = False
    # Re-force loggers AFTER KOPF's own startup reconfigures them
    for _name in _KOPF_LOGGER_NAMES:
        _kl = logging.getLogger(_name)
        _kl.handlers.clear()
        _kl.addHandler(stderr_handler)
        _kl.propagate = False
        _kl.setLevel(logging.WARNING)


@kopf.on.field('v1', 'pods', field='status.containerStatuses')
def monitor_pod_crashes(new, name, namespace, **kwargs):
    """Intercept pods in CrashLoopBackOff or OOMKilled in real-time."""
    for status in new or []:
        state = status.get('state', {})
        last_state = status.get('lastState', {})
        
        # Check current waiting state (for CrashLoopBackOff, ErrImagePull, Probe failures)
        waiting = state.get('waiting', {})
        w_reason = waiting.get('reason')
        if w_reason in ['CrashLoopBackOff', 'CreateContainerConfigError', 'CreateContainerError', 'ErrImagePull', 'ImagePullBackOff', 'InvalidImageName']:
            alert_id = f"pod:{namespace}/{name}"
            cluster_alerts[alert_id] = {
                "type": "PodAlert",
                "pod": name,
                "namespace": namespace,
                "reason": w_reason,
                "exit_code": "N/A",
                "message": waiting.get('message', 'No additional message'),
            }
            logger.warning(f"ALERT: {name} in {namespace} is waiting — {w_reason}")

        # Check termination reasons
        terminated = last_state.get('terminated', {})
        t_reason = terminated.get('reason')
        if t_reason in ['OOMKilled', 'Error', 'ContainerCannotRun']:
            alert_id = f"pod:{namespace}/{name}"
            cluster_alerts[alert_id] = {
                "type": "PodAlert",
                "pod": name,
                "namespace": namespace,
                "reason": t_reason,
                "exit_code": terminated.get('exitCode'),
                "message": terminated.get('message', 'No additional message'),
            }
            logger.warning(f"ALERT: {name} in {namespace} crashed — {t_reason}")

@kopf.on.field('v1', 'nodes', field='status.conditions')
def monitor_node_conditions(new, name, **kwargs):
    """Intercept node distress conditions like MemoryPressure or NotReady."""
    for condition in new or []:
        ctype = condition.get('type')
        cstatus = condition.get('status')
        
        # Usually format is 'True' or 'False' as strings
        is_bad = False
        message = condition.get('message', 'No message')
        
        if ctype == 'Ready' and cstatus == 'False':
            is_bad = True
        elif ctype in ['MemoryPressure', 'DiskPressure', 'PIDPressure', 'NetworkUnavailable'] and cstatus == 'True':
            is_bad = True
            
        if is_bad:
            alert_id = f"node:{name}"
            cluster_alerts[alert_id] = {
                "type": "NodeAlert",
                "node": name,
                "reason": ctype,
                "message": message,
            }
            logger.warning(f"ALERT: Node {name} is in bad state — {ctype}: {message}")
        else:
            # Clear it if it recovered
            alert_id = f"node:{name}"
            if alert_id in cluster_alerts and cluster_alerts[alert_id].get('reason') == ctype:
                del cluster_alerts[alert_id]
                logger.info(f"Node {name} recovered from {ctype}")


def run_kopf():
    """Run the KOPF operator with stdout completely suppressed."""
    # Nuclear option: redirect stdout to devnull inside the KOPF thread
    # so that ANY print() or misconfigured logger inside KOPF/asyncio
    # cannot pollute the MCP stdio channel.
    sys.stdout = open(os.devnull, 'w')
    try:
        asyncio.run(kopf.operator(verbose=False))
    except Exception as e:
        logger.error(f"KOPF operator crashed: {e}")
    finally:
        sys.stdout = sys.__stdout__


threading.Thread(target=run_kopf, daemon=True).start()

# ==========================================================================
# REGISTER ALL TOOL MODULES
# ==========================================================================
cluster.register(mcp)
workloads.register(mcp)
pods.register(mcp)
networking.register(mcp)
storage.register(mcp)
config_tools.register(mcp)
rbac.register(mcp)
scaling.register(mcp)
diagnostics.register(mcp, cluster_alerts)
remediation.register(mcp, cluster_alerts)
custom_resources.register(mcp)

logger.info("All tool modules registered successfully.")

# ==========================================================================
# START MCP SERVER
# ==========================================================================
if __name__ == "__main__":
    logger.info("Starting K8s SRE MCP Server...")
    mcp.run()