"""Read-only post-apply AWS verification; never changes resources."""
from preflight import aws

cluster = aws("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
nodes = aws("eks", "describe-nodegroup", "--cluster-name", "banking-dev", "--nodegroup-name", "banking-dev-workers")["nodegroup"]
if cluster["status"] != "ACTIVE" or nodes["status"] != "ACTIVE" or nodes["health"]["issues"]:
    raise RuntimeError("Cluster/node group is not healthy.")
for addon in ["vpc-cni", "kube-proxy", "coredns", "metrics-server", "eks-pod-identity-agent"]:
    result = aws("eks", "describe-addon", "--cluster-name", "banking-dev", "--addon-name", addon)["addon"]
    if result["status"] != "ACTIVE" or result["health"]["issues"]:
        raise RuntimeError("Add-on is not healthy: " + addon)
for repository in ["banking-dev-account", "banking-dev-payment"]:
    result = aws("ecr", "describe-repositories", "--repository-names", repository)["repositories"][0]
    if result["imageTagMutability"] != "IMMUTABLE" or not result["imageScanningConfiguration"]["scanOnPush"]:
        raise RuntimeError("ECR immutable tags/scanning are not enabled.")
print("Verified ACTIVE cluster, healthy managed node group and five add-ons, and both immutable scan-on-push ECR repositories.")
