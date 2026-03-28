<p align="center">
  <img src="kubog.png" alt="Kubernetes" width="1200"/>
</p>

<h1 align="center">⚙️ mcp-server-kubog</h1>

<p align="center">
  <strong>A Kubernetes SRE MCP Server with real-time crash monitoring powered by KOPF</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#tools-reference">Tools</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#license">License</a>
</p>

---

## Overview

**mcp-server-kopf** is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that gives AI assistants deep, real-time access to Kubernetes clusters. Built on [FastMCP](https://github.com/jlowin/fastmcp) and the [Kubernetes Operator Pythonic Framework (KOPF)](https://kopf.readthedocs.io/), it combines **45 read/write tools** across 10 functional categories with a **background crash-loop monitor** that detects `OOMKilled`, `CrashLoopBackOff`, and error states the moment they occur.

Connect it to any MCP-compatible client (Claude Desktop, Cursor, custom agents) and let your AI copilot observe, diagnose, and remediate Kubernetes issues without ever leaving the conversation.

---

## Features

- 🔴 **Real-time crash monitoring** — KOPF operator watches `containerStatuses` and raises alerts for `OOMKilled`, `CrashLoopBackOff`, and `Error` states instantly.
- 🛠️ **45 SRE tools** — From cluster overview to active remediation, grouped into logical categories.
- 🔄 **Read _and_ write operations** — Not just observability: scale deployments, restart workloads, rollback revisions, patch OOM limits, cordon/uncordon nodes.
- 📡 **MCP-native** — Works out-of-the-box with any MCP client via `stdio` transport.
- 🏗️ **Modular architecture** — Each tool category lives in its own module; easy to extend or customize.

---

## Why KOPF Instead of kubectl?

Projects like [mcp-server-kubernetes](https://pypi.org/project/mcp-kubernetes-server) give AI assistants Kubernetes access by shelling out to `kubectl` under the hood. This works, but it has significant limitations. **mcp-server-kopf** takes a fundamentally different approach by using the **Kubernetes Python client** for API calls and **KOPF** for real-time event watching.

| | **kubectl-based servers** | **mcp-server-kopf** |
|---|---|---|
| **API interaction** | Shells out to `kubectl` → parses text output | Native Python client → structured objects |
| **Real-time monitoring** | ❌ Poll-based or absent | ✅ KOPF operator watches events in real-time |
| **Crash detection** | Manual — must query pods | Automatic — alerts surface the instant a pod crashes |
| **Error handling** | String parsing of CLI output | Typed exceptions from the Kubernetes API |
| **Dependency** | Requires `kubectl` binary on the host | No external binaries — pure Python |
| **Remediation** | Limited to `kubectl` verbs | Direct API patches (scale, restart, rollback, OOM fix) |
| **Output format** | Raw CLI text (fragile to parse) | Structured, consistent, purpose-built responses |
| **Extensibility** | Add shell commands | Add Python functions with full API access |
| **Security** | Arbitrary command execution risk | Scoped API calls — no shell injection surface |
| **Closed-loop SRE** | ❌ Detect and diagnose only | ✅ Detect → diagnose → remediate in one conversation |

### Key Advantages

- **🔴 Proactive, not reactive** — The KOPF background operator continuously watches pod status. Crash alerts exist *before* you even ask. With kubectl-based servers, the AI has to explicitly run commands to discover problems.
- **🔒 No shell, no risk** — kubectl-based tools execute arbitrary shell commands, which introduces injection risks and requires the binary to be installed. This server uses only the official Kubernetes Python client.
- **🧱 Structured data** — Instead of parsing `kubectl get pods -o wide` text output (which can break across versions), every tool returns clean, structured strings built from typed API objects.
- **⚡ Closed-loop remediation** — Beyond observation, the server can *act*: patch resource limits, trigger rollout restarts, rollback deployments, and cordon nodes — all through safe, scoped API calls.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    MCP Client                        │
│         (Claude Desktop / Cursor / Agent)            │
└─────────────────────┬────────────────────────────────┘
                      │  stdio (MCP protocol)
┌─────────────────────▼────────────────────────────────┐
│                   main.py                            │
│  ┌──────────────┐  ┌─────────────────────────────┐   │
│  │  FastMCP     │  │  KOPF Background Operator   │   │
│  │  Server      │  │  (Thread)                   │   │
│  │              │  │                             │   │
│  │  45 Tools    │  │  Watches pod status fields  │   │
│  │  registered  │◄─┤  Populates cluster_alerts   │   │
│  └──────────────┘  └─────────────────────────────┘   │
└─────────────────────┬────────────────────────────────┘
                      │  kubernetes python client
┌─────────────────────▼────────────────────────────────┐
│              Kubernetes API Server                   │
└──────────────────────────────────────────────────────┘
```

---

## Tools Reference

### 🖥️ Cluster Overview
| Tool | Description |
|---|---|
| `list_nodes` | List all nodes with status, roles, version, CPU/memory capacity |
| `describe_node` | Detailed node info: conditions, taints, allocatable resources, labels |
| `list_namespaces` | List all namespaces with status and labels |
| `cluster_resource_usage` | Aggregate CPU/memory requests vs allocatable capacity |

### 📦 Workloads
| Tool | Description |
|---|---|
| `list_deployments` | List Deployments with replicas, ready, available, age |
| `describe_deployment` | Deployment detail: strategy, conditions, containers, labels |
| `list_statefulsets` | List StatefulSets with ready/desired replicas |
| `list_daemonsets` | List DaemonSets with desired/ready/available counts |
| `list_replicasets` | List ReplicaSets with owner references |
| `list_jobs` | List Jobs with status, completions, duration |
| `describe_job` | Job detail: completions, parallelism, containers, conditions |
| `list_cronjobs` | List CronJobs with schedule, last run, active count |

### 🐳 Pods
| Tool | Description |
|---|---|
| `list_pods` | List pods with status, restarts, node, IP (supports label selectors) |
| `describe_pod` | Full pod detail: conditions, containers, volumes, events |
| `get_pod_logs` | Retrieve pod logs with container, tail lines, and previous-container support |
| `get_pod_resource_usage` | Live CPU/memory usage via Metrics API |

### 🌐 Networking
| Tool | Description |
|---|---|
| `list_services` | List Services with type, ClusterIP, external IP, ports |
| `describe_service` | Service detail with selector, endpoints, ports |
| `list_ingresses` | List Ingresses with hosts, paths, backends |
| `list_network_policies` | List NetworkPolicies with selectors and rule counts |
| `list_endpoints` | List Endpoints with ready/not-ready addresses |

### 💾 Storage
| Tool | Description |
|---|---|
| `list_pvs` | List PersistentVolumes with capacity, access, reclaim, status |
| `list_pvcs` | List PVCs with status, capacity, bound volume |
| `describe_pvc` | PVC detail with conditions and events |
| `list_storage_classes` | List StorageClasses with provisioner, reclaim policy, parameters |

### ⚙️ Configuration
| Tool | Description |
|---|---|
| `list_configmaps` | List ConfigMaps with key counts |
| `get_configmap` | Read ConfigMap data (keys and values) |
| `list_secrets` | List Secrets with type and key counts (values hidden) |
| `describe_secret` | Show Secret keys/sizes; optionally decode base64 values |

### 🔐 RBAC
| Tool | Description |
|---|---|
| `list_service_accounts` | List ServiceAccounts with secret counts |
| `list_roles` | List Roles with rule counts |
| `list_cluster_roles` | List ClusterRoles with rule counts |
| `list_role_bindings` | List RoleBindings with subjects and role references |
| `list_cluster_role_bindings` | List ClusterRoleBindings with subjects and role references |

### 📈 Scaling
| Tool | Description |
|---|---|
| `list_hpas` | List HPAs with min/max/current replicas and CPU targets |
| `scale_deployment` | Manually scale a Deployment to N replicas |
| `scale_statefulset` | Manually scale a StatefulSet to N replicas |

### 🩺 Diagnostics
| Tool | Description |
|---|---|
| `get_active_alerts` | View real-time crash alerts detected by the KOPF monitor |
| `get_recent_events` | Retrieve Warning-type events in a namespace |
| `get_all_events` | Retrieve all recent events (Normal + Warning) |
| `list_resource_quotas` | Show ResourceQuotas with used vs hard limits |
| `list_limit_ranges` | Show LimitRanges with default/max/min container limits |

### 🔧 Remediation
| Tool | Description |
|---|---|
| `fix_oom_resources` | Patch memory limits on the owning Deployment of an OOMKilled pod |
| `restart_deployment` | Perform a rollout restart of a Deployment |
| `rollback_deployment` | Rollback a Deployment to the previous revision |
| `cordon_node` | Mark a node as unschedulable |
| `uncordon_node` | Mark a node as schedulable again |

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- Access to a Kubernetes cluster (local or remote)
- A valid `kubeconfig` file or in-cluster service account
- [metrics-server](https://github.com/kubernetes-sigs/metrics-server) installed (optional — required for `get_pod_resource_usage`)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/mcp-server-kopf.git
cd mcp-server-kopf

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install mcp[cli] kopf kubernetes
```

### Running the server

```bash
python main.py
```

The server starts in `stdio` mode, ready for any MCP client to connect.

---

## Configuration

### Kubernetes Context

By default the server loads the `workercluster` context from your local kubeconfig:

```python
config.load_kube_config(context="workercluster")
```

To use a different context, edit the `context` parameter in `main.py`, or remove it entirely to use the current default context. When running inside a Kubernetes cluster, the server automatically falls back to `load_incluster_config()`.

### MCP Client Configuration

Add the server to your MCP client's configuration. For example, in **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "k8s-sre": {
      "command": "python",
      "args": ["/path/to/mcp-server-kopf/main.py"]
    }
  }
}
```

---

## Project Structure

```
mcp-server-kopf/
├── main.py                 # Entry point — FastMCP server + KOPF crash monitor
├── tools/
│   ├── __init__.py
│   ├── cluster.py          # Nodes, namespaces, cluster resource usage
│   ├── workloads.py        # Deployments, StatefulSets, DaemonSets, Jobs, CronJobs
│   ├── pods.py             # Pod listing, describe, logs, metrics
│   ├── networking.py       # Services, Ingresses, Endpoints, NetworkPolicies
│   ├── storage.py          # PVs, PVCs, StorageClasses
│   ├── config.py           # ConfigMaps, Secrets
│   ├── rbac.py             # Roles, ClusterRoles, Bindings, ServiceAccounts
│   ├── scaling.py          # HPAs, manual scaling
│   ├── diagnostics.py      # Alerts, events, quotas, limit ranges
│   └── remediation.py      # OOM fix, restart, rollback, cordon/uncordon
├── LICENSE                 # Apache 2.0
└── README.md
```

---

## How the Crash Monitor Works

A **KOPF operator** runs in a background thread alongside the MCP server. It watches the `status.containerStatuses` field on all pods across the cluster:

1. When a container enters `OOMKilled`, `CrashLoopBackOff`, or `Error` state, the operator captures the alert.
2. Alerts are stored in a shared `cluster_alerts` dictionary.
3. The `get_active_alerts` tool exposes these to the AI assistant.
4. The assistant can then investigate with `describe_pod`, `get_pod_logs`, and remediate with `fix_oom_resources`, `restart_deployment`, or `rollback_deployment`.

This creates a **closed-loop SRE workflow**: detect → diagnose → remediate — all from within a single conversation.

---

## Example Workflow

```
You:    "Are there any issues on the cluster?"
AI:     → calls get_active_alerts()
        🚨 Pod payment-svc-7f8b5 in production crashed — OOMKilled

You:    "Show me the logs"
AI:     → calls get_pod_logs("payment-svc-7f8b5", "production", previous=True)
        java.lang.OutOfMemoryError: Java heap space ...

You:    "Increase memory and restart it"
AI:     → calls fix_oom_resources("payment-svc-7f8b5", "production", "1Gi")
        ✅ Deployment 'payment-svc' memory updated to 1Gi
        → calls restart_deployment("payment-svc", "production")
        ✅ Rollout restart initiated
```

---

## Contributing

Contributions are welcome! Each tool category is a self-contained module in `tools/` — to add a new tool:

1. Pick the appropriate module (or create a new one).
2. Define your function inside the `register(mcp)` function.
3. Decorate it with `@mcp.tool()`.
4. Import and register it in `main.py`.

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.
