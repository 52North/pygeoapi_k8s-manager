---
name: Report a bug
about: Report a bug or regression for the pygeoapi-k8s-manager
title: '[BUG]: '
labels: 'bug, needs-triage'
assignees: ''
---

### 🐛 The Bug

A clear and concise description of what the bug is.
What happened, and what did you expect to happen instead?

### 🔁 Steps to Reproduce

Please provide the exact steps to reproduce this bug.

1.
2.
3.

**HOW to Reproduce (IMPORTANT):**

Please provide one of the following so we can replicate the failure:

* **pytest Test:** (Preferred) A minimal, self-contained `pytest` test case that fails.
* **`kind` Cluster Setup:** If the bug is infrastructure or cluster-related, please provide a `kind` cluster configuration file and the `kubectl` commands (or curl/HTTP requests) needed to trigger the problem.

### 📄 Relevant Logs & Configuration

Please paste any relevant log output from the `pygeoapi-k8s-manager` pod or from pygeoapi itself.

**Logs:**

(Please paste logs here)

**Configuration:**

Please paste relevant snippets of your pygeoapi configuration, Kubernetes manifests (e.g., Deployment, ServiceAccount), or the process definitions involved.

```yaml
(Please paste configuration snippets here)
```

💻 Your Environment
Please fill in these details to help us diagnose the issue.

* pygeoapi-k8s-manager version: (e.g., 0.5.0 or main @ commit-hash)
* pygeoapi version: (e.g., 1.14.0)
* Kubernetes Server version: (e.g., v1.28.2, GKE, EKS, kind v0.20.0)
* kubernetes (Python client) version: (e.g., 28.1.0)
* Service Account Permissions: (e.g., "cluster-admin" or "read-only" or "able to create/delete Jobs in namespace X")

Additional Context: (Any other details about your setup, e.g., Ingress controller, NetworkPolicies, etc.)
