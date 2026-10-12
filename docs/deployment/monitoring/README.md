# Monitoring preparation and evidence limits

Both APIs emit single-line JSON console logs with route templates, status, latency
and trace ID, excluding request bodies, query strings and database credentials.
The private /metrics endpoint exposes request/error rates, latency histogram,
process CPU seconds/working-set bytes, storage readiness and payment event/outbox
metrics. Process measurements are not Kubernetes Pod requests/limits or actual
Fargate billing capacity. Verify kubectl top and CapacityProvisioned after live EKS.

prometheus.yml, alerts.yml and grafana-dashboard.json are reviewable configuration,
not installed services. Prometheus/Grafana may run as approved ordinary Deployments
on the banking-dev Fargate profile, with explicit resource/cost/storage review.
Do not install a node exporter/DaemonSet or claim node/NetworkPolicy enforcement.
Do not expose metrics publicly. Existing ingress routes only the API paths.

The configuration discovers each annotated Running API Pod in banking-dev and
selects its named http container port. It does not scrape a load-balanced ClusterIP
for counters or hardcode Pod addresses. The approved operator installs the prepared
namespace-only Pod discovery RBAC so every replica is scraped separately.
Shared outbox gauges use max, not sum,
because every Payment Pod observes the same database. Health alerts supplement
CloudWatch's database/SQS alarms. Alertmanager/notification routing must use an
actually approved receiver; no email/SMS recipient or delivery success is invented.

aws-logging.yaml is a proposed shared-cluster ConfigMap for the Fargate built-in
router. The approved operator must create/review aws-observability with
aws-observability=enabled, preserve any existing shared logging configuration and
review the Banking namespace filter. It is not part of the application Helm release.
Use the precreated encrypted log group, scoped execution-role delivery permissions
and approved CloudWatch KMS policy; no automatic log-group creation. Existing Pods
need an approved rollout after logging changes. Retention and ingestion cost require
separate approval. Verify actual merged State.Status log records before enabling
CloudWatch HTTP-error metric/alarm assertions. No logging daemon was deployed.

Offline evidence: metric exposition and credential/cardinality checks against real
API containers; valid Prometheus configuration/rules and sample rule evaluations.
Live evidence still required: all Pod scrape targets, fresh logs, actual CPU/memory,
dashboard data, alert transitions, delivery/ownership and recovery timestamps.

References: [prometheus-net](https://github.com/prometheus-net/prometheus-net),
[Fargate built-in logging](https://docs.aws.amazon.com/eks/latest/userguide/fargate-logging.html).
