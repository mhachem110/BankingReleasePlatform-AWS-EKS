"""Read-only live prerequisites. Called only inside a separately approved workflow."""
import json
import os
import subprocess
from pathlib import Path
from data_guard import ACCOUNT, REGION, configuration, cost_review, digest, require
from data_iam import monitoring_trust, session_cap


def aws(service, operation, *args):
    result = subprocess.run(["aws", service, operation, *args, "--region", REGION, "--output", "json", "--no-cli-pager"],
                            check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout or "{}")


def verify(role, attached, key, topic, policy, values, env):
    require(role["Arn"] == values["monitoring_role_arn"] and not role.get("PermissionsBoundary"), "Monitoring role identity/boundary requires review")
    require(role["AssumeRolePolicyDocument"] == monitoring_trust(), "Dedicated monitoring trust must restrict exact database/account")
    require("arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole" in
            {p["PolicyArn"] for p in attached}, "Actual AWS-managed Enhanced Monitoring permissions required")
    require(key.get("Arn") == values["kms_key_arn"] and key.get("KeyState") == "Enabled" and
            key.get("KeySpec") == "SYMMETRIC_DEFAULT" and key.get("KeyUsage") == "ENCRYPT_DECRYPT", "Approved enabled encryption key required")
    require(topic.get("TopicArn") == values["alert_topic_arn"] and int(topic.get("SubscriptionsConfirmed", "0")) > 0,
            "Approved alert topic must have a confirmed destination; delivery still requires live acceptance")
    expected = session_cap(values, env["DATA_SESSION_POLICY_ARN"])
    require(digest(policy) == env["DATA_SESSION_POLICY_SHA256"] == digest(expected), "Actual managed session cap changed or exceeds approved scope")


def main():
    env = os.environ
    values = configuration(env)
    cost_review(json.loads(env["DATA_COST_REVIEW_JSON"]), values)
    require(aws("sts", "get-caller-identity")["Account"] == ACCOUNT, "Wrong account")
    role = aws("iam", "get-role", "--role-name", values["monitoring_role_arn"].split("/")[-1])["Role"]
    attached = aws("iam", "list-attached-role-policies", "--role-name", role["RoleName"])["AttachedPolicies"]
    key = aws("kms", "describe-key", "--key-id", values["kms_key_arn"])["KeyMetadata"]
    topic = aws("sns", "get-topic-attributes", "--topic-arn", values["alert_topic_arn"])["Attributes"]
    policy = aws("iam", "get-policy", "--policy-arn", env["DATA_SESSION_POLICY_ARN"])["Policy"]
    document = aws("iam", "get-policy-version", "--policy-arn", policy["Arn"], "--version-id", policy["DefaultVersionId"])["PolicyVersion"]["Document"]
    verify(role, attached, key, topic, document, values, env)
    service_role = aws("iam", "get-role", "--role-name", "AWSServiceRoleForRDS")["Role"]
    require(service_role["Arn"] == f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS", "Administrator must preauthorize the RDS service-linked role")
    cluster = aws("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
    require(cluster["status"] == "ACTIVE" and cluster["resourcesVpcConfig"]["vpcId"] == values["vpc_id"] and
            cluster["resourcesVpcConfig"]["clusterSecurityGroupId"] == values["cluster_security_group_id"], "Phase 3 must be actually deployed/verified first")
    options = aws("rds", "describe-orderable-db-instance-options", "--engine", "postgres", "--engine-version", values["engine_version"],
                  "--db-instance-class", values["instance_class"])["OrderableDBInstanceOptions"]
    require(any(o.get("StorageType") == "gp3" and o.get("SupportsStorageEncryption") and o.get("SupportsEnhancedMonitoring") for o in options),
            "Exact approved engine/class must support reviewed storage/encryption/monitoring")
    require(not any(d["DBInstanceIdentifier"] == "banking-dev-postgres" for d in aws("rds", "describe-db-instances")["DBInstances"]), "Database name exists; recovery requires separate reviewed scope")
    require(not any(d["DBSubnetGroupName"] == "banking-dev-database" for d in aws("rds", "describe-db-subnet-groups")["DBSubnetGroups"]), "Database subnet group already exists")
    require(not any(d["DBParameterGroupName"] == "banking-dev-postgres17" for d in aws("rds", "describe-db-parameter-groups")["DBParameterGroups"]), "Database parameter group already exists")
    require(not aws("ec2", "describe-security-groups", "--filters", "Name=vpc-id,Values="+values["vpc_id"], "Name=group-name,Values=banking-dev-database")["SecurityGroups"], "Database security group already exists")
    queues = aws("sqs", "list-queues", "--queue-name-prefix", "banking-dev-payments").get("QueueUrls", [])
    require(not any(q.rsplit("/", 1)[-1] in {"banking-dev-payments", "banking-dev-payments-dlq"} for q in queues), "Data queue name exists; never adopt automatically")
    for name in ("/banking/banking-dev/application", "/aws/rds/instance/banking-dev-postgres/postgresql", "/aws/rds/instance/banking-dev-postgres/upgrade"):
        require(not any(g["logGroupName"] == name for g in aws("logs", "describe-log-groups", "--log-group-name-prefix", name)["logGroups"]), "Data log group already exists")
    require(not aws("cloudwatch", "describe-alarms", "--alarm-name-prefix", "banking-dev-")["MetricAlarms"], "Banking alarms already exist; review bounded recovery separately")
    Path("data-prerequisites.json").write_text(json.dumps({"account":ACCOUNT, "region":REGION, "cluster":"banking-dev",
        "policy_sha256":digest(document), "key_arn":key["Arn"], "monitoring_role_arn":role["Arn"],
        "alert_topic_arn":topic["TopicArn"], "scope":"read-only metadata; not live application acceptance"}, indent=2), encoding="utf-8")
    print("Verified data prerequisite metadata. No AWS writes or credential-value reads.")


if __name__ == "__main__":
    main()
