"""Read-only service verification after separately authorized saved-plan apply."""
import json
from pathlib import Path
from data_guard import ACCOUNT, REGION, ENVIRONMENT, NAME, require
from data_preflight import aws


def verify(database, source, dead, values):
    expected = {"DBInstanceIdentifier":NAME + "-postgres", "DBInstanceStatus":"available", "Engine":"postgres",
        "EngineVersion":values["engine_version"], "DBInstanceClass":values["instance_class"], "DBName":"banking",
        "PubliclyAccessible":False, "StorageEncrypted":True, "KmsKeyId":values["kms_key_arn"], "MultiAZ":False,
        "DeletionProtection":True, "BackupRetentionPeriod":7, "AllocatedStorage":20, "MaxAllocatedStorage":40,
        "IAMDatabaseAuthenticationEnabled":True, "MonitoringInterval":60, "MonitoringRoleArn":values["monitoring_role_arn"]}
    require(all(database.get(k) == v for k,v in expected.items()), "Actual database security/capacity/version mismatch")
    require(len(database.get("VpcSecurityGroups", [])) == 1 and database["VpcSecurityGroups"][0].get("Status") == "active",
            "Require exactly one active database SG; an extra group can weaken isolation")
    secret = database.get("MasterUserSecret") or {}
    require(secret.get("SecretStatus") == "active" and secret.get("KmsKeyId") == values["kms_key_arn"] and
            secret.get("SecretArn", "").startswith(f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:rds!db-"), "RDS-managed operator secret must be healthy and encrypted")
    subnet = database["DBSubnetGroup"]
    require(subnet["VpcId"] == values["vpc_id"] and {s["SubnetIdentifier"] for s in subnet["Subnets"]} == set(values["database_subnet_ids"]) and
            len({s["SubnetAvailabilityZone"]["Name"] for s in subnet["Subnets"]}) == 2, "Actual isolated subnet group mismatch")
    require(source.get("QueueArn") == f"arn:aws:sqs:{REGION}:{ACCOUNT}:{NAME}-payments" and
            dead.get("QueueArn") == f"arn:aws:sqs:{REGION}:{ACCOUNT}:{NAME}-payments-dlq", "Actual queue identities mismatch")
    require(source.get("KmsMasterKeyId") == dead.get("KmsMasterKeyId") == values["kms_key_arn"] and
            source.get("MessageRetentionPeriod") == "86400" and dead.get("MessageRetentionPeriod") == "1209600" and
            source.get("VisibilityTimeout") == "30" and source.get("MaximumMessageSize") == "4096", "Actual queue encryption/retry/retention mismatch")
    redrive = json.loads(source["RedrivePolicy"])
    require(redrive.get("deadLetterTargetArn") == dead["QueueArn"] and int(redrive.get("maxReceiveCount",0)) == 5, "Actual redrive target/count mismatch")
    require(json.loads(dead["RedriveAllowPolicy"]) == {"redrivePermission":"byQueue", "sourceQueueArns":[source["QueueArn"]]}, "Actual DLQ source scope mismatch")
    for queue in (source, dead):
        policy = json.loads(queue["Policy"])
        require(policy == {"Version":"2012-10-17", "Statement":[{"Sid":"DenyUnencryptedTransport", "Effect":"Deny",
            "Principal":"*", "Action":"sqs:*", "Resource":queue["QueueArn"], "Condition":{"Bool":{"aws:SecureTransport":"false"}}}]}, "Actual TLS queue policy mismatch")
    return {"database":"available/private/encrypted/backed-up", "queues":"encrypted/TLS/redrive verified",
            "application_acceptance":"pending: runtime TLS, credentials, durable Pod replacement, delivery, notification and rollback"}


def main():
    values = json.loads(Path("data.tfvars.json").read_text())
    outputs = json.loads(Path("data-outputs.json").read_text())["interface"]["value"]
    database = aws("rds", "describe-db-instances", "--db-instance-identifier", NAME + "-postgres")["DBInstances"][0]
    source = aws("sqs", "get-queue-attributes", "--queue-url", outputs["payment_queue_url"], "--attribute-names", "All")["Attributes"]
    dead = aws("sqs", "get-queue-attributes", "--queue-url", outputs["dead_letter_queue_url"], "--attribute-names", "All")["Attributes"]
    result = verify(database, source, dead, values)
    parameters = aws("rds", "describe-db-parameters", "--db-parameter-group-name", NAME + "-postgres17")["Parameters"]
    actual = {p["ParameterName"]:p.get("ParameterValue") for p in parameters}
    require(all(actual.get(p) == "1" for p in ("rds.force_ssl", "log_connections", "log_disconnections")), "Actual database parameters mismatch")
    group = aws("ec2", "describe-security-groups", "--group-ids", database["VpcSecurityGroups"][0]["VpcSecurityGroupId"])["SecurityGroups"][0]
    require(group["GroupName"] == NAME + "-database" and group["VpcId"] == values["vpc_id"] and group["IpPermissionsEgress"] == [] and
            len(group["IpPermissions"]) == 1, "Actual database SG scope mismatch")
    rule = group["IpPermissions"][0]
    require(rule["IpProtocol"] == "tcp" and rule["FromPort"] == rule["ToPort"] == 5432 and not rule.get("IpRanges") and not rule.get("Ipv6Ranges") and
            [g["GroupId"] for g in rule["UserIdGroupPairs"]] == [values["cluster_security_group_id"]], "Actual ingress scope mismatch")
    for name in (f"/banking/{NAME}/application", f"/aws/rds/instance/{NAME}-postgres/postgresql", f"/aws/rds/instance/{NAME}-postgres/upgrade"):
        groups = aws("logs", "describe-log-groups", "--log-group-name-prefix", name)["logGroups"]
        require(any(g["logGroupName"] == name and g.get("retentionInDays") == 30 and g.get("kmsKeyId") == values["kms_key_arn"] for g in groups), "Actual data log encryption/retention mismatch")
    alarms = aws("cloudwatch", "describe-alarms", "--alarm-name-prefix", NAME + "-")["MetricAlarms"]
    names = {NAME + "-"+n for n in ("database_cpu", "database_storage", "queue_age", "dead_letters", "http_errors")}
    require({a["AlarmName"] for a in alarms} == names and all(a["ActionsEnabled"] and a["AlarmActions"] == [values["alert_topic_arn"]] for a in alarms), "Actual owned alarms/action mismatch")
    result["logs_alarms"] = "encrypted logs and five owned alarm destinations verified; actual delivery pending"
    Path("data-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
