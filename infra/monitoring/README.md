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
prod-prometheus.yml and prod-prometheus-rbac.yaml prepare separate banking-prod
discovery with no dev access. Use distinct approved collectors/destinations; retain
the same reusable alert rules/dashboard definitions. Extra collector Pods, storage,
quota sizing and notification destinations require separate review/approval.
Shared outbox gauges use max, not sum,
because every Payment Pod observes the same database. Health alerts supplement
CloudWatch's database/SQS alarms. Alertmanager/notification routing must use an
actually approved receiver; no email/SMS recipient or delivery success is invented.

aws-logging.yaml is a proposed shared-cluster ConfigMap for the Fargate built-in
router. The approved operator must create/review aws-observability with
aws-observability=enabled, preserve any existing shared logging configuration and
review the Banking namespace filter. It is not part of the application Helm release.
CRI parsing precedes JSON merging. A supported rewrite_tag filter uses actual
Kubernetes namespace metadata to route dev and prod to their separate precreated
groups. Original tags are retained in the new tags for distinct streams; the new
tags do not match kube.*, avoiding emitter loops. Other namespaces are excluded.
Both groups must exist with approved encryption/retention before this configuration
is applied. The execution role needs separately authorized exact-group stream/event
access to both; no automatic log-group creation or cross-environment runtime secret
permissions are introduced. Actual Fargate acceptance/log arrival remains mandatory.
Use the precreated encrypted log group, scoped execution-role delivery permissions
and approved CloudWatch KMS policy; no automatic log-group creation. Existing Pods
need an approved rollout after logging changes. Retention and ingestion cost require
separate approval. Verify actual merged State.Status log records before enabling
CloudWatch HTTP-error metric/alarm assertions. No logging daemon was deployed.

Offline evidence: metric exposition and credential/cardinality checks against real
API containers; valid Prometheus configuration/rules and sample rule evaluations.
validate-log-routing.py also runs a digest-pinned AWS for Fluent Bit container with
network disabled: actual grep/rewrite filters route metadata-shaped dev/prod fixtures
once each and exclude system/stage fixtures. Both Prometheus configurations and
namespace RBAC validate offline. This tests routing semantics, not the actual managed
Fargate router's metadata enrichment, CloudWatch delivery or alert notification.
Live evidence still required: all Pod scrape targets, fresh logs, actual CPU/memory,
dashboard data, alert transitions, delivery/ownership and recovery timestamps.

References: [prometheus-net](https://github.com/prometheus-net/prometheus-net),
[Fargate built-in logging](https://docs.aws.amazon.com/eks/latest/userguide/fargate-logging.html).
