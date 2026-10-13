"""Protected first creation of two reviewed project policies; no role mutations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from bootstrap_authorization import verify as verify_authorization
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BOUNDARY, BUCKET, digest, require

KEY = 'banking-release-platform/shared/policy-prerequisites/terraform.tfstate'
CAP = f'arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-IamPrerequisites'
POLICIES = {'boundary': (BOUNDARY, 'BankingServicePermissionsBoundary.json'),
            'iam_cap': (CAP, 'BankingTerraformProvisioner-IamPrerequisites.json')}
FOLDER = Path(__file__).resolve().parents[2] / 'iam/provisioning/proposed'
TAGS = dict(Project='BankingReleasePlatform', Environment='shared', ManagedBy='Terraform', Owner='MahmoudHachem', Purpose='CloudEngineerTraining', Component='policy-iam')


def configuration(env):
    require(env.get('GITHUB_REPOSITORY') == 'mhachem110/BankingReleasePlatform-AWS-EKS' and env.get('GITHUB_REF') == 'refs/heads/dev', 'Only reviewed Banking/dev may publish policies')
    require(env.get('POLICY_PUBLISH_ENABLED') == 'true' and env.get('AWS_OPERATIONS_ENABLED') == 'true' and env.get('CLEANUP_ENABLED') != 'true', 'Explicit policy publication window; cleanup must be disabled')
    require(env.get('BOOTSTRAP_STATE_READY') == 'true' and env.get('ROLE_ARN') == BOOTSTRAP and env.get('AWS_EXPECTED_ACCOUNT_ID') == ACCOUNT and env.get('AWS_REGION') == REGION and env.get('TF_STATE_BUCKET') == BUCKET, 'Wrong verified identity/account/backend')
    require(env.get('OPERATION') in {'plan', 'apply'}, 'First creation only; no update/delete/import')
    if env['OPERATION'] == 'apply':
        require(env.get('APPROVAL') == 'APPLY-REVIEWED-BANKING-POLICIES', 'Separate saved-plan policy apply review required')
    return dict(account=ACCOUNT, region=REGION, state_key=KEY,
                documents={key: digest(document(key)) for key in POLICIES})


def document(key):
    return json.loads((FOLDER / POLICIES[key][1]).read_text())


def backend():
    return dict(bucket=BUCKET, region=REGION, key=KEY, encrypt=True, use_lockfile=True,
                allowed_account_ids=[ACCOUNT], workspace_key_prefix='banking-release-platform/_workspaces')


def session_policy(write=False):
    bucket = 'arn:aws:s3:::' + BUCKET
    rows = [dict(Effect='Allow', Action=['sts:GetCallerIdentity', 'iam:GetRole', 'iam:GetRolePolicy', 'iam:ListRolePolicies', 'iam:ListAttachedRolePolicies', 'iam:GetPolicy', 'iam:GetPolicyVersion', 'iam:SimulatePrincipalPolicy'], Resource='*'),
            dict(Effect='Allow', Action=['s3:Get*', 's3:ListBucket'], Resource=bucket),
            dict(Effect='Allow', Action=['s3:GetObject'] + (['s3:PutObject'] if write else []), Resource=bucket + '/' + KEY),
            dict(Effect='Allow', Action=['s3:GetObject', 's3:PutObject', 's3:DeleteObject'], Resource=bucket + '/' + KEY + '.tflock')]
    if write:
        rows.append(dict(Effect='Allow', Action=['iam:CreatePolicy', 'iam:TagPolicy'], Resource=[v[0] for v in POLICIES.values()],
                         Condition={'StringEquals': {'aws:RequestTag/Project': 'BankingReleasePlatform', 'aws:RequestTag/Environment': 'shared', 'aws:RequestTag/ManagedBy': 'Terraform'}}))
    cap = json.dumps(dict(Version='2012-10-17', Statement=rows), separators=(',', ':'))
    require(len(cap) <= 2048, 'Policy publisher inline cap exceeds AWS limit')
    return cap


def read(service, operation, *args):
    require(operation in {'get-caller-identity', 'get-role', 'get-role-policy', 'list-role-policies', 'list-attached-role-policies', 'get-policy', 'get-policy-version', 'simulate-principal-policy'}, 'Outside read-only policy inspection')
    result = subprocess.run(['aws', service, operation, *args, '--region', REGION, '--output', 'json', '--no-cli-pager'], capture_output=True, text=True, encoding='utf-8', timeout=60)
    if result.returncode:
        if operation == 'get-policy' and '(NoSuchEntity)' in result.stderr:
            return {'absent': True}
        raise ValueError(result.stderr.strip())
    return json.loads(result.stdout)


def preflight(call=read):
    identity = call('sts', 'get-caller-identity')
    require(identity.get('Account') == ACCOUNT and identity.get('Arn', '').startswith(f'arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/'), 'Wrong publisher OIDC identity')
    authorization = verify_authorization(call)
    simulations = {}
    for key, (arn, _) in POLICIES.items():
        require(call('iam', 'get-policy', '--policy-arn', arn).get('absent') is True, 'Policy exists; do not adopt or replace it: ' + arn)
        context = [{'ContextKeyName': 'aws:RequestedRegion', 'ContextKeyValues': ['us-east-1'], 'ContextKeyType': 'string'}]
        context += [{'ContextKeyName': 'aws:RequestTag/' + k, 'ContextKeyValues': [v], 'ContextKeyType': 'string'} for k, v in dict(TAGS, Name=arn.split('/')[-1]).items()]
        result = call('iam', 'simulate-principal-policy', '--policy-source-arn', BOOTSTRAP, '--action-names', 'iam:CreatePolicy', 'iam:TagPolicy', '--resource-arns', arn, '--context-entries', json.dumps(context))
        rows = result.get('EvaluationResults', [])
        require(len(rows) == 2 and {r.get('EvalActionName') for r in rows} == {'iam:CreatePolicy', 'iam:TagPolicy'} and all(r.get('EvalDecision') == 'allowed' and r.get('EvalResourceName') == arn and not r.get('MissingContextValues') for r in rows), 'Policy publication simulation denied/incomplete')
        simulations[key] = result
    return dict(identity=identity, authorization=authorization, simulations=simulations, documents={k: digest(document(k)) for k in POLICIES})


def plan_review(plan, *, effective_tags=True):
    require(plan.get('applyable') is True and plan.get('complete') is True and not plan.get('errored') and not plan.get('deferred_changes'), 'Complete saved policy plan required')
    items = [r for r in plan.get('resource_changes', []) if r.get('mode') == 'managed']
    expected = {'terraform_data.authorization'} | {f'aws_iam_policy.project["{k}"]' for k in POLICIES}
    require(len(items) == 3 and {r['address'] for r in items} == expected, 'Only two reviewed policies and local account guard may be created')
    for row in items:
        change = row['change']; require(change['actions'] == ['create'] and not change.get('importing') and not row.get('previous_address'), 'No adoption/update/delete/role mutation')
        if row['address'] == 'terraform_data.authorization':
            require(row['type'] == 'terraform_data', 'Wrong local guard type'); continue
        key = row['address'].split('"')[1]; value = change.get('after') or {}; arn, _ = POLICIES[key]
        require(row['type'] == 'aws_iam_policy' and value.get('name') == arn.split('/')[-1] and value.get('path') == '/' and value.get('name_prefix') is None, 'Wrong policy name/path')
        require(json.loads(value.get('policy') or '{}') == document(key), 'Policy document differs from reviewed source')
        for field in (['tags', 'tags_all'] if effective_tags else ['tags']):
            require(value.get(field) == dict(TAGS, Name=arn.split('/')[-1]), 'Policy ownership tags are unresolved or changed')
    return dict(managed_creates=3, managed_updates=0, managed_deletes=0, role_mutations=0,
                policies={key: dict(arn=arn, sha256=digest(document(key))) for key, (arn, _) in POLICIES.items()})


def verify(call=read):
    verify_authorization(call)
    result = {}
    for key, (arn, _) in POLICIES.items():
        meta = call('iam', 'get-policy', '--policy-arn', arn)['Policy']
        require(meta.get('Arn') == arn and meta.get('Path') == '/' and meta.get('AttachmentCount') == 0 and meta.get('PermissionsBoundaryUsageCount') == 0, 'New policy identity or usage differs')
        tags = {r['Key']: r['Value'] for r in meta.get('Tags', [])}
        require(tags == dict(TAGS, Name=arn.split('/')[-1]), 'Live policy ownership changed')
        version = call('iam', 'get-policy-version', '--policy-arn', arn, '--version-id', meta['DefaultVersionId'])['PolicyVersion']
        require(digest(version['Document']) == digest(document(key)), 'Live policy document differs')
        result[key] = dict(arn=arn, sha256=digest(version['Document']), version=meta['DefaultVersionId'])
    return dict(account=ACCOUNT, region=REGION, policies=result, bootstrap_unchanged=True,
                no_policy_attached_to_bootstrap=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['inputs', 'write-cap', 'preflight', 'plan', 'verify', 'saved']); args = parser.parse_args()
    values = configuration(os.environ)
    if args.command == 'inputs':
        Path('policies-config.json').write_text(json.dumps(values, indent=2))
        Path('policies.tfbackend.json').write_text(json.dumps(backend(), indent=2))
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out: out.write('session_policy=' + session_policy() + '\n')
    elif args.command == 'write-cap':
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out: out.write('session_policy=' + session_policy(True) + '\n')
    elif args.command == 'preflight':
        Path('policies-preflight.json').write_text(json.dumps(preflight(), indent=2))
    elif args.command == 'plan':
        report = plan_review(json.loads(Path('policies-plan.json').read_text()))
        report['saved_plan_sha256'] = hashlib.sha256(Path('policies.tfplan').read_bytes()).hexdigest()
        Path('policies-plan-review.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))
    elif args.command == 'saved':
        require(values == json.loads(Path('reviewed/policies-config.json').read_text()), 'Reviewed policy inputs changed')
        require(backend() == json.loads(Path('reviewed/policies.tfbackend.json').read_text()), 'Reviewed policy backend changed')
        report = json.loads(Path('reviewed/policies-plan-review.json').read_text())
        require(hashlib.sha256(Path('reviewed/policies.tfplan').read_bytes()).hexdigest() == report['saved_plan_sha256'] == os.environ.get('REVIEWED_DIGEST'), 'Reviewed binary digest changed')
        require(plan_review(json.loads(Path('policies-plan.json').read_text())) == {k: v for k, v in report.items() if k != 'saved_plan_sha256'}, 'Saved policy plan differs from reviewed source')
    else:
        Path('policies-verification.json').write_text(json.dumps(verify(), indent=2))
