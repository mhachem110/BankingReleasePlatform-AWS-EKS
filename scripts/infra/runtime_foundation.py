"""Create a real project key/operator through the existing saved-plan reviews."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from bootstrap_authorization import verify as verify_authorization
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, digest, require
from cleanup_guard import aws
import subprocess
import tempfile

KEY = 'banking-release-platform/shared/runtime-foundation/terraform.tfstate'
OPERATOR = f'arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-operator'
ALIAS = 'alias/banking-release-platform-runtime'
FOLDER = Path(__file__).resolve().parents[2] / 'iam/runtime-foundation'
TAGS = dict(Project='BankingReleasePlatform', Environment='shared', ManagedBy='Terraform', Owner='MahmoudHachem', Purpose='CloudEngineerTraining', Component='runtime-foundation')


def document(name):
    return json.loads((FOLDER / (name + '.json')).read_text())


def configuration(env):
    require(env.get('GITHUB_REPOSITORY') == 'mhachem110/BankingReleasePlatform-AWS-EKS' and env.get('GITHUB_REF') == 'refs/heads/dev', 'Reviewed Banking/dev only')
    require(env.get('RUNTIME_FOUNDATION_ENABLED') == env.get('AWS_OPERATIONS_ENABLED') == env.get('BOOTSTRAP_STATE_READY') == 'true' and env.get('CLEANUP_ENABLED') != 'true', 'Explicit creation window and completed backend required')
    require(env.get('ROLE_ARN') == BOOTSTRAP and env.get('AWS_EXPECTED_ACCOUNT_ID') == ACCOUNT and env.get('AWS_REGION') == REGION and env.get('TF_STATE_BUCKET') == BUCKET, 'Wrong foundation identity/account/backend')
    require(env.get('OPERATION') in {'plan','apply'}, 'Initial foundation creation only')
    if env['OPERATION'] == 'apply': require(env.get('APPROVAL') == 'APPLY-REVIEWED-BANKING-FOUNDATION', 'Separate saved-plan review required')
    return dict(account=ACCOUNT, region=REGION, state_key=KEY, documents={n:digest(document(n)) for n in ['key-policy','operator-trust','operator-policy']})


def backend():
    return dict(bucket=BUCKET,region=REGION,key=KEY,encrypt=True,use_lockfile=True,allowed_account_ids=[ACCOUNT],workspace_key_prefix='banking-release-platform/_workspaces')


def session_policy(write=False):
    bucket='arn:aws:s3:::'+BUCKET
    rows=[dict(Effect='Allow',Action=['sts:GetCallerIdentity','iam:Get*','iam:List*','kms:DescribeKey','kms:Get*','kms:List*'],Resource='*'),
          dict(Effect='Allow',Action=['s3:Get*','s3:ListBucket'],Resource=bucket),
          dict(Effect='Allow',Action=['s3:GetObject']+(['s3:PutObject'] if write else []),Resource=bucket+'/'+KEY),
          dict(Effect='Allow',Action=['s3:GetObject','s3:PutObject','s3:DeleteObject'],Resource=bucket+'/'+KEY+'.tflock')]
    if write:
        rows += [dict(Effect='Allow',Action=['iam:CreateRole','iam:TagRole','iam:PutRolePolicy'],Resource=OPERATOR),
                 dict(Effect='Allow',Action='kms:CreateKey',Resource='*',Condition={'StringEquals':{'aws:RequestedRegion':REGION,'aws:RequestTag/Project':'BankingReleasePlatform','aws:RequestTag/Environment':'shared','aws:RequestTag/Name':'banking-runtime'}}),
                 dict(Effect='Allow',Action=['kms:EnableKeyRotation','kms:PutKeyPolicy','kms:TagResource','kms:CreateAlias'],Resource=f'arn:aws:kms:{REGION}:{ACCOUNT}:key/*',Condition={'StringEquals':{'aws:RequestedRegion':REGION,'aws:ResourceTag/Project':'BankingReleasePlatform','aws:ResourceTag/Environment':'shared','aws:ResourceTag/Name':'banking-runtime'}}),
                 dict(Effect='Allow',Action='kms:CreateAlias',Resource=f'arn:aws:kms:{REGION}:{ACCOUNT}:alias/banking-release-platform-runtime')]
    cap=json.dumps(dict(Version='2012-10-17',Statement=rows),separators=(',',':'))
    require(len(cap)<=2048,'Foundation STS cap exceeds inline limit')
    return cap


def read_state():
    """Read only the foundation state; missing state is distinct from access denial."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'state.json'
        result = subprocess.run(['aws', 's3api', 'get-object', '--bucket', BUCKET,
            '--key', KEY, '--expected-bucket-owner', ACCOUNT, '--region', REGION,
            '--output', 'json', str(path)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            require('(NoSuchKey)' in result.stderr, 'Cannot read foundation state: ' + result.stderr.strip())
            return {}
        return json.loads(path.read_text())


def existing_outputs(state, call=aws):
    """Resume only a complete, owned native state whose actual resources verify."""
    from cleanup_guard import rows, state_review, inventory
    managed = rows(state)
    if not managed:
        return None
    require({r['address'] for r in managed} == inventory('runtime-foundation'),
            'Incomplete foundation state requires recovery; never recreate or destroy it automatically')
    state_review(state, dict(target='runtime-foundation', key=KEY), {})
    outputs = state.get('outputs', {})
    require(outputs.get('state_key', {}).get('value') == KEY and
            outputs.get('contract_version', {}).get('value') == 1,
            'Foundation state output contract differs')
    key = next(r['values'] for r in managed if r['type'] == 'aws_kms_key')
    role = next(r['values'] for r in managed if r['type'] == 'aws_iam_role')
    require(outputs.get('kms_key_arn', {}).get('value') == key['arn'] and
            outputs.get('operator_role_arn', {}).get('value') == role['arn'],
            'Foundation outputs must reference their own managed resources')
    verify(outputs, call)
    return outputs


def preflight(call=aws, state=None):
    verify_authorization(call)
    identity=call('sts','get-caller-identity')
    require(identity.get('Account')==ACCOUNT and identity.get('Arn','').startswith(f'arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/'),'Wrong foundation OIDC session')
    outputs = existing_outputs(read_state() if state is None else state, call)
    if outputs:
        return dict(identity=identity, resume=True, verified=True,
                    kms_key_arn=outputs['kms_key_arn']['value'], operator_role_arn=OPERATOR,
                    documents={n:digest(document(n)) for n in ['key-policy','operator-trust','operator-policy']})
    require(call('iam','get-role','--role-name',OPERATOR.split('/')[-1],absent_codes=('NoSuchEntity',)).get('absent'),'Operator already exists; do not adopt or mutate it')
    require(not any(r.get('AliasName')==ALIAS for r in call('kms','list-aliases')['Aliases']),'Runtime alias exists; do not adopt another key')
    return dict(identity=identity,documents={n:digest(document(n)) for n in ['key-policy','operator-trust','operator-policy']})


def plan_review(plan,effective_tags=True):
    require(plan.get('complete') is True and not plan.get('errored') and not plan.get('deferred_changes'),'Complete foundation plan required')
    resources=[r for r in plan.get('resource_changes',[]) if r.get('mode')=='managed']
    expected={'terraform_data.authorization','aws_kms_key.runtime','aws_kms_alias.runtime','aws_iam_role.operator','aws_iam_role_policy.operator'}
    require(len(resources)==5 and {r['address'] for r in resources}==expected,'Exact key/operator inventory required')
    actions = {tuple(r['change']['actions']) for r in resources}
    require(actions in ({('create',)}, {('no-op',)}), 'Only initial creation or a complete unchanged foundation may run; no partial recreation')
    creating = actions == {('create',)}
    require(plan.get('applyable') is True if creating else plan.get('applyable') is False,
            'Plan applyability differs from resource actions')
    key_value = next(r['change']['after'] for r in resources if r['type'] == 'aws_kms_key')
    for r in resources:
        c=r['change'];v=c.get('after') or {}; kind=r['type']
        require(kind==r['address'].split('.')[0] and not c.get('importing') and not r.get('previous_address'),'No update/delete/import/replacement')
        if kind in {'aws_kms_key','aws_iam_role'}:
            name='banking-runtime' if kind=='aws_kms_key' else OPERATOR.split('/')[-1]
            for f in ['tags','tags_all'] if effective_tags else ['tags']:
                require(v.get(f)==dict(TAGS,Name=name),'Resolved foundation ownership required')
        if kind=='aws_kms_key':
            require(all(v.get(k)==value for k,value in dict(key_usage='ENCRYPT_DECRYPT',customer_master_key_spec='SYMMETRIC_DEFAULT',multi_region=False,is_enabled=True,enable_key_rotation=True,rotation_period_in_days=365,deletion_window_in_days=7,bypass_policy_lockout_safety_check=False).items()) and json.loads(v.get('policy') or '{}')==document('key-policy'),'Reviewed symmetric rotated key policy required')
        if kind=='aws_kms_alias':
            require(v.get('name')==ALIAS and not v.get('name_prefix'), 'Exact runtime alias required')
            require(c.get('after_unknown',{}).get('target_key_id') is True if creating else
                    v.get('target_key_id') == key_value.get('key_id') and bool(key_value.get('key_id')),
                    'Alias must reference the same project key')
        if kind=='aws_iam_role': require(v.get('name')==OPERATOR.split('/')[-1] and v.get('path')=='/' and v.get('permissions_boundary') in (None, '') and v.get('force_detach_policies') is False and v.get('max_session_duration')==3600 and json.loads(v.get('assume_role_policy') or '{}')==document('operator-trust'),'Exact operator trust required')
        if kind=='aws_iam_role_policy': require(v.get('name')=='BankingOperator' and v.get('role')==OPERATOR.split('/')[-1] and json.loads(v.get('policy') or '{}')==document('operator-policy'),'Operator cannot gain other AWS permissions')
    return dict(managed_creates=5 if creating else 0,managed_updates=0,managed_deletes=0,operator_arn=OPERATOR,documents={n:digest(document(n)) for n in ['key-policy','operator-trust','operator-policy']},cost_review={'key_storage_usd_per_month_before_rotation':1,'source':'https://aws.amazon.com/kms/pricing/','notes':'Hourly prorated; KMS requests and future rotations are additional. No EKS, NAT, runner or databases in this plan.'})


def verify(outputs,call=aws):
    verify_authorization(call)
    key=outputs['kms_key_arn']['value']; require(key.startswith(f'arn:aws:kms:{REGION}:{ACCOUNT}:key/'),'Wrong actual project key')
    meta=call('kms','describe-key','--key-id',key)['KeyMetadata']
    require(meta.get('Arn')==key and meta.get('KeyState')=='Enabled' and meta.get('KeySpec')=='SYMMETRIC_DEFAULT' and meta.get('KeyUsage')=='ENCRYPT_DECRYPT' and meta.get('MultiRegion') is False,'Actual key differs')
    require(json.loads(call('kms','get-key-policy','--key-id',key,'--policy-name','default')['Policy'])==document('key-policy'),'Actual key policy differs')
    rotation=call('kms','get-key-rotation-status','--key-id',key)
    require(rotation.get('KeyRotationEnabled') is True and rotation.get('RotationPeriodInDays')==365,'Key rotation differs')
    tags={r['TagKey']:r['TagValue'] for r in call('kms','list-resource-tags','--key-id',key)['Tags']}
    require(tags==dict(TAGS,Name='banking-runtime'),'Actual key ownership differs')
    aliases=call('kms','list-aliases','--key-id',key)['Aliases'];require(any(r.get('AliasName')==ALIAS and r.get('TargetKeyId')==meta['KeyId'] for r in aliases),'Alias target differs')
    role=call('iam','get-role','--role-name',OPERATOR.split('/')[-1])['Role']
    require(outputs['operator_role_arn']['value']==role.get('Arn')==OPERATOR and role.get('Path')=='/' and role.get('AssumeRolePolicyDocument')==document('operator-trust') and not role.get('PermissionsBoundary'),'Actual operator trust differs')
    require({r['Key']:r['Value'] for r in role.get('Tags',[])}==dict(TAGS,Name=OPERATOR.split('/')[-1]),'Actual operator ownership differs')
    require(not call('iam','list-attached-role-policies','--role-name',role['RoleName'])['AttachedPolicies'] and call('iam','list-role-policies','--role-name',role['RoleName'])['PolicyNames']==['BankingOperator'],'Unexpected operator grants')
    require(call('iam','get-role-policy','--role-name',role['RoleName'],'--policy-name','BankingOperator')['PolicyDocument']==document('operator-policy'),'Actual operator permissions differ')
    return dict(verified=True,account=ACCOUNT,region=REGION,kms_key_arn=key,operator_role_arn=OPERATOR,bootstrap_unchanged=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['inputs','preflight','write-cap','plan','saved','verify']);args=p.parse_args();config=configuration(os.environ)
    if args.command=='inputs':
        Path('foundation-config.json').write_text(json.dumps(config,indent=2));Path('foundation.tfbackend.json').write_text(json.dumps(backend(),indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('session_policy='+session_policy()+'\n')
    elif args.command=='write-cap':
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('session_policy='+session_policy(True)+'\n')
    elif args.command=='preflight':
        report=preflight();Path('foundation-preflight.json').write_text(json.dumps(report,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('interface_json='+json.dumps({k:report[k] for k in ['verified','kms_key_arn','operator_role_arn'] if k in report},separators=(',',':'))+'\n')
    elif args.command=='plan':
        report=plan_review(json.loads(Path('foundation-plan.json').read_text()));report['saved_plan_sha256']=hashlib.sha256(Path('foundation.tfplan').read_bytes()).hexdigest();Path('foundation-plan-review.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('apply_required='+str(report['managed_creates'] > 0).lower()+'\n')
    elif args.command=='saved':
        require(config==json.loads(Path('reviewed/foundation-config.json').read_text()) and backend()==json.loads(Path('reviewed/foundation.tfbackend.json').read_text()),'Reviewed foundation inputs/backend changed')
        report=json.loads(Path('reviewed/foundation-plan-review.json').read_text());require(hashlib.sha256(Path('reviewed/foundation.tfplan').read_bytes()).hexdigest()==report['saved_plan_sha256']==os.environ.get('REVIEWED_DIGEST'),'Saved binary digest differs')
        require(plan_review(json.loads(Path('foundation-plan.json').read_text()))=={k:v for k,v in report.items() if k!='saved_plan_sha256'},'Saved plan differs from reviewed source')
    else:
        report=verify(json.loads(Path('foundation-outputs.json').read_text()));Path('foundation-verification.json').write_text(json.dumps(report,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('interface_json='+json.dumps(report,separators=(',',':'))+'\n')
