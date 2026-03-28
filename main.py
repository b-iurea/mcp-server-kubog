import asyncio
import sys
import logging
import threading
import kopf
from mcp.server.fastmcp import FastMCP
from kubernetes import client, config

# Tools modules
from tools import cluster, workloads, pods, networking, storage
from tools import rbac, scaling, diagnostics, remediation
from tools import config as config_tools  # avoid clash with kubernetes.config

# ==========================================================================
# LOGGING
# ==========================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("sre-mcp-server")

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

@kopf.on.field('v1', 'pods', field='status.containerStatuses')
def monitor_pod_crashes(new, name, namespace, **kwargs):
    """Intercept pods in CrashLoopBackOff or OOMKilled in real-time."""
    for status in new or []:
        state = status.get('lastState', {}).get('terminated', {})
        reason = state.get('reason')
        if reason in ['OOMKilled', 'Error', 'CrashLoopBackOff']:
            alert_id = f"{namespace}/{name}"
            cluster_alerts[alert_id] = {
                "pod": name,
                "namespace": namespace,
                "reason": reason,
                "exit_code": state.get('exitCode'),
                "message": state.get('message', 'No additional message'),
            }
            logger.warning(f"🚨 ALERT: {name} in {namespace} crashed — {reason}")

def run_kopf():
    asyncio.run(kopf.operator())

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

logger.info("All tool modules registered successfully.")

# ==========================================================================
# START MCP SERVER
# ==========================================================================
if __name__ == "__main__":
    logger.info("Starting K8s SRE MCP Server...")
    mcp.run()