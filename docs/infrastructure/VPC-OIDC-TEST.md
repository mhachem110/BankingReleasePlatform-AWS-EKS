# Protected OIDC and initial VPC test

The owner's instruction authorizes an actual VPC test with the existing
`cloudbatch818-mahmoud-cloudops-bootstrap` identity. The protected audit
[38337253266](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38337253266)
successfully authenticated that identity in account 866934333672. Its current
CloudOpsTrackerBootstrap policy grants `ec2:*` on Resource `*`; the separate
Retail-name restriction concerns IAM writes and PassRole. Missing Banking IAM
grants do not by themselves prevent VPC creation. A successful live apply, rather
than a policy snapshot or simulation, determines actual VPC authorization.

The VPC workflow now uses `infra/network-seed`, containing only
`terraform_data.prerequisites` and `module.network.aws_vpc.this`. The latter has
the same resource address, provider, CIDR, DNS and tags as the full platform.
Both use the existing dev/platform backend key and native locking. The full
platform therefore continues from this state without imports, address moves or
recreating the VPC. IAM/KMS/EKS readiness guards in the full platform are retained.
The seed and full platform share one workflow concurrency group.

The seed needs neither an IAM remote state nor a nominated key/operator. Its
1,944-character inline STS cap restricts the session to a Banking-tagged Ohio VPC,
DNS modifications on that tagged VPC, metadata reads and the exact platform
state/lock objects. DeleteObject is restricted to `.tflock`; no DeleteVpc,
IAM/KMS write, subnet, public IP, gateway, NAT, database or EKS allow exists.
The session cap limits the existing role; it does not create an IAM grant.

Set repository AWS_OPERATIONS_ENABLED and NETWORK_SEED_ENABLED to true for the
authorized window. Existing bootstrap environment review/dev-only restriction
and owner-only PR protections remain required. Default VPC_SEED_INPUTS_JSON is
`{}` and selects 10.70.0.0/16 and Owner=MahmoudHachem; optional cost_center must be
an actual assigned value. Credentials do not belong in input variables.

Dispatch network-prerequisites.yml from reviewed dev, operation=apply,
approval=APPLY-REVIEWED-BANKING-VPC-SEED. Personally approve the plan deployment.
The workflow checks actual OIDC identity, fresh VPC/CIDR collisions, the tagged
CreateVpc API with --dry-run, and existing bucket protections before saving a
creation-only plan. Only AWS DryRunOperation confirms that probe's authorization;
every actual denial is retained. Expect two managed entries:
one VPC plus the local account guard. Review its tags, state key, scope and saved
binary SHA256 before the second bootstrap deployment approval. Apply downloads
only the same-run artifact and checks binary/input/backend/cap equality.

Verification reads the native platform state, actual VPC owner/CIDR/tags, actual
default security group membership and both DNS attributes. A subsequent seed
plan must be zero-change. Publish the verified interface for the later full
platform plan, then return both execution switches to false. Any AWS denial,
collision, partial deployment or state mismatch stops for bounded review;
no automatic deletion, role editing, import or force-unlock is provided.

This is the actual project's initial VPC, retained for later networking/EKS.
It has no workload, subnet or Internet gateway. Its automatically generated
default security group is not claimed closed until the full platform manages it.
The separately missing Banking IAM/KMS/runner prerequisites still affect EKS
and application deployment. VPC success does not prove those permissions or
complete a cluster acceptance milestone.
