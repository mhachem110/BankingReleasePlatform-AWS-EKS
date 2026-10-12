"""Verify the real release identity before any Helm mutation. Never changes RBAC."""
from common import run


def verify_access(namespace, command=run):
    if namespace not in {"banking-dev", "banking-prod"}:
        raise ValueError("Only approved demonstration namespaces are allowed")
    other = "banking-prod" if namespace == "banking-dev" else "banking-dev"

    def allowed(verb, resource, target=None):
        args = ["kubectl", "auth", "can-i", verb, resource]
        if target:
            args += ["-n", target]
        answer = command(args, capture=True, check=False).strip()
        if answer not in {"yes", "no"}:
            raise ValueError("Authorization diagnostic failed: " + " ".join(args))
        return answer == "yes"

    for verb, resource in [("create", "deployments.apps"), ("patch", "deployments.apps"),
                           ("create", "secrets"), ("get", "pods"), ("get", "pods/log"),
                           ("create", "pods/portforward"), ("create", "services")]:
        if not allowed(verb, resource, namespace):
            raise ValueError("Required namespace release permission is missing")
    for target in (other, "kube-system"):
        for resource in ("deployments.apps", "services", "serviceaccounts", "secrets", "pods", "pods/log"):
            for verb in ("get", "create", "patch", "delete"):
                if allowed(verb, resource, target):
                    raise ValueError("Release identity has access outside its namespace")
    for verb, resource in [("create", "clusterroles.rbac.authorization.k8s.io"),
                           ("create", "clusterrolebindings.rbac.authorization.k8s.io"),
                           ("delete", "namespaces"), ("patch", "nodes")]:
        if allowed(verb, resource):
            raise ValueError("Release identity has cluster mutation permissions")
    for resource in ("roles.rbac.authorization.k8s.io", "rolebindings.rbac.authorization.k8s.io"):
        if allowed("create", resource, namespace):
            raise ValueError("Release identity can change its authorization")
    print("PASS: namespace release rights and cross-namespace/cluster mutation denials")
