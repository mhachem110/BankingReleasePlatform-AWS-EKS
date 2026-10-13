"""Publish source-generated session caps without changing any role permissions."""
import subprocess
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from bootstrap_authorization import verify as authorization
from cleanup_guard import aws, rows
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, canonical, digest, require
from provisioner_policies import generate
from runtime_foundation import OPERATOR, existing_outputs, read_state as foundation_state
from network_seed import existing_seed, load_state as network_state

KEY = 'banking-release-platform/shared/platform-caps/terraform.tfstate'
NAMES = {f'BankingTerraformProvisioner-Platform-{i}' for i in [1,2,3]}
ARNS = {name:f'arn:aws:iam::{ACCOUNT}:policy/{name}' for name in NAMES}
TAGS = dict(Project='BankingReleasePlatform', Environment='shared', ManagedBy='Terraform',
            Owner='MahmoudHachem', Purpose='CloudEngineerTraining', Component='platform-caps')


def documents(bindings):
    require(set(bindings) == {'kms_key_arn','operator_role_arn','vpc_id','default_security_group_id'}, 'Exact dependency bindings required')
    require(re.fullmatch(f'arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}',bindings['kms_key_arn'])
            and bindings['operator_role_arn'] == OPERATOR, 'Actual owned foundation required')
    for name,prefix in [('vpc_id','vpc'),('default_security_group_id','sg')]:
        require(re.fullmatch(prefix+r'-[a-f0-9]{17}',bindings[name]), 'Actual network ID required')
    generated=generate(key=bindings['kms_key_arn'],vpc=bindings['vpc_id'],sg=bindings['default_security_group_id'])
    result={name:json.loads(json.dumps(generated[name+'.json']).replace(
        f'arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__',OPERATOR)) for name in sorted(NAMES)}
    require(all('__' not in canonical(doc) and len(canonical(doc))<=6144 for doc in result.values()), 'Unresolved or oversized session cap')
    return result


def configuration(env):
    require(env.get('GITHUB_REPOSITORY')=='mhachem110/BankingReleasePlatform-AWS-EKS' and
            env.get('GITHUB_REF')=='refs/heads/dev', 'Publish only reviewed Banking/dev')
    require(env.get('AWS_OPERATIONS_ENABLED')==env.get('BOOTSTRAP_STATE_READY')=='true' and
            env.get('CLEANUP_ENABLED')!='true', 'Verified backend and authorized creation window required')
    require(env.get('ROLE_ARN')==BOOTSTRAP and env.get('AWS_REGION')==REGION and
            env.get('AWS_EXPECTED_ACCOUNT_ID')==ACCOUNT and env.get('TF_STATE_BUCKET')==BUCKET, 'Wrong identity or backend')
    require(env.get('OPERATION') in {'plan','apply'}, 'No update, destroy or state repair')
    if env['OPERATION']=='apply':require(env.get('APPROVAL')=='APPLY-REVIEWED-BANKING-PLATFORM-CAPS','Separate saved-plan review required')
    foundation=json.loads(env.get('FOUNDATION_INTERFACE_JSON') or '{}')
    network=json.loads(env.get('NETWORK_INTERFACE_JSON') or '{}')
    require(foundation.get('verified') is True and network.get('verified') is True, 'Apply and verify dependencies before publishing their caps')
    require(network.get('account')==ACCOUNT and network.get('region')==REGION, 'Wrong verified network account/Region')
    bindings={k:foundation[k] for k in ['kms_key_arn','operator_role_arn']}
    bindings.update({k:network[k] for k in ['vpc_id','default_security_group_id']})
    docs=documents(bindings)
    return dict(bindings=bindings,documents={name:canonical(doc) for name,doc in docs.items()})


def backend():
    return dict(bucket=BUCKET,region=REGION,key=KEY,encrypt=True,use_lockfile=True,
                allowed_account_ids=[ACCOUNT],workspace_key_prefix='banking-release-platform/_workspaces')


def session_policy(write=False):
    bucket='arn:aws:s3:::'+BUCKET
    statements=[dict(Effect='Allow',Action=['sts:GetCallerIdentity','iam:Get*','iam:List*','kms:DescribeKey','kms:Get*','kms:List*','ec2:Describe*'],Resource='*'),
        dict(Effect='Allow',Action=['s3:Get*','s3:ListBucket'],Resource=bucket),
        dict(Effect='Allow',Action='s3:GetObject',Resource=bucket+'/banking-release-platform/*/terraform.tfstate'),
        dict(Effect='Allow',Action=['s3:GetObject','s3:PutObject','s3:DeleteObject'],Resource=bucket+'/'+KEY+'.tflock')]
    if write:
        statements += [dict(Effect='Allow',Action=['iam:CreatePolicy','iam:TagPolicy'],Resource=sorted(ARNS.values()),
            Condition={'StringEquals':{'aws:RequestTag/Project':'BankingReleasePlatform','aws:RequestTag/Environment':'shared','aws:RequestTag/ManagedBy':'Terraform'}}),
            dict(Effect='Allow',Action='s3:PutObject',Resource=bucket+'/'+KEY)]
    cap=canonical(dict(Version='2012-10-17',Statement=statements));require(len(cap)<=2048,'STS cap exceeds limit')
    return cap


def read_state():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'state.json'
        result=subprocess.run(['aws','s3api','get-object','--bucket',BUCKET,'--key',KEY,
            '--expected-bucket-owner',ACCOUNT,'--region',REGION,str(path)],capture_output=True,text=True,timeout=60)
        if result.returncode:
            require('(NoSuchKey)' in result.stderr,'Cannot inspect cap state: '+result.stderr.strip());return {}
        return json.loads(path.read_text())


def inventory():
    return {'terraform_data.authorization'} | {f'aws_iam_policy.project["{name}"]' for name in NAMES}


def state_review(state,config):
    managed=rows(state);require({r['address'] for r in managed}<=inventory(),'Unknown cap state addresses')
    for row in managed:
        if row['type']=='terraform_data':continue
        value=row['values'];name=value.get('name')
        require(name in NAMES and value.get('arn')==value['id']==ARNS[name] and value.get('path')=='/', 'Unknown policy identity')
        require(value.get('tags')==dict(TAGS,Name=name) and json.loads(value.get('policy') or '{}')==json.loads(config['documents'][name]),'Owned cap document or tags changed')
    return managed


def verify_policy(name,config,call=aws):
    policy=call('iam','get-policy','--policy-arn',ARNS[name])['Policy']
    require(policy.get('Arn')==ARNS[name] and policy.get('Path')=='/' and policy.get('AttachmentCount')==0 and
            policy.get('PermissionsBoundaryUsageCount')==0,'A session cap must not be a role grant or boundary')
    require({t['Key']:t['Value'] for t in policy.get('Tags',[])}==dict(TAGS,Name=name),'Policy ownership differs')
    version=call('iam','get-policy-version','--policy-arn',ARNS[name],'--version-id',policy['DefaultVersionId'])['PolicyVersion']
    require(version.get('Document')==json.loads(config['documents'][name]),'Live cap differs from finalized reviewed source')
    return dict(arn=ARNS[name],sha256=digest(version['Document']),version=policy['DefaultVersionId'])


def preflight(config,call=aws,state=None):
    authorization(call)
    identity=call('sts','get-caller-identity')
    require(identity.get('Account')==ACCOUNT and identity.get('Arn','').startswith(
        f'arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/'), 'Wrong publisher OIDC session')
    foundation=existing_outputs(foundation_state(),call)
    require(foundation and foundation['kms_key_arn']['value']==config['bindings']['kms_key_arn'] and
            foundation['operator_role_arn']['value']==OPERATOR,'Foundation binding changed')
    network=existing_seed(network_state(),{'owner':'MahmoudHachem','vpc_cidr':'10.70.0.0/16'},call)
    require(network and all(network[k]==config['bindings'][k] for k in ['vpc_id','default_security_group_id']),'Network binding changed')
    managed=state_review(read_state() if state is None else state,config)
    owned={r['values']['name'] for r in managed if r['type']=='aws_iam_policy'}
    for name in NAMES:
        if name in owned:verify_policy(name,config,call)
        else:require(call('iam','get-policy','--policy-arn',ARNS[name],absent_codes=('NoSuchEntity',)).get('absent'),'Existing policy outside native state; no adoption')
    return dict(verified=True,identity=identity,bindings=config['bindings'],existing_policies=sorted(owned))


def plan_review(plan,config,effective_tags=True):
    require(plan.get('complete') is True and not plan.get('errored') and not plan.get('deferred_changes'),'Complete cap plan required')
    managed=[r for r in plan.get('resource_changes',[]) if r.get('mode')=='managed']
    require(len(managed)==4 and {r['address'] for r in managed}==inventory(),'Exact three policies and account guard required')
    creates=0
    for row in managed:
        change=row['change'];value=change.get('after') or {}
        require(change['actions'] in [['create'],['no-op']] and not change.get('importing') and not row.get('previous_address'),'No update, deletion, replacement or import')
        creates+=change['actions']==['create']
        if row['address']=='terraform_data.authorization':require(row['type']=='terraform_data','Wrong local guard');continue
        name=row['address'].split('"')[1]
        require(row['type']=='aws_iam_policy' and value.get('name')==name and value.get('path')=='/' and not value.get('name_prefix') and
                json.loads(value.get('policy') or '{}')==json.loads(config['documents'][name]),'Policy differs from source-generated cap')
        for field in ['tags','tags_all'] if effective_tags else ['tags']:
            require(value.get(field)==dict(TAGS,Name=name),'Unresolved or changed ownership')
    require(plan.get('applyable') is (creates>0),'Plan applyability differs from actions')
    return dict(managed_creates=creates,managed_updates=0,managed_deletes=0,role_mutations=0,
                policies=[dict(arn=ARNS[name],sha256=digest(json.loads(config['documents'][name]))) for name in sorted(NAMES)])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['inputs','preflight','plan','saved','write-cap','verify']);args=parser.parse_args()
    config=configuration(os.environ)
    if args.command=='inputs':
        Path('caps-config.json').write_text(json.dumps(config,indent=2));Path('caps.tfvars.json').write_text(json.dumps(config,indent=2))
        Path('caps.tfbackend.json').write_text(json.dumps(backend(),indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('session_policy='+session_policy()+'\n')
    elif args.command=='write-cap':
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('session_policy='+session_policy(True)+'\n')
    elif args.command=='preflight':
        report=preflight(config);Path('caps-preflight.json').write_text(json.dumps(report,indent=2))
        if set(report['existing_policies'])==NAMES:
            proof=[dict(arn=ARNS[name],sha256=digest(json.loads(config['documents'][name]))) for name in sorted(NAMES)]
            with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('policy_review_json='+json.dumps(proof,separators=(',',':'))+'\n')
    elif args.command=='plan':
        report=plan_review(json.loads(Path('caps-plan.json').read_text()),config)
        report['saved_plan_sha256']=hashlib.sha256(Path('caps.tfplan').read_bytes()).hexdigest();Path('caps-plan-review.json').write_text(json.dumps(report,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('apply_required='+str(report['managed_creates']>0).lower()+'\n')
    elif args.command=='saved':
        require(config==json.loads(Path('reviewed/caps-config.json').read_text()) and backend()==json.loads(Path('reviewed/caps.tfbackend.json').read_text()),'Reviewed inputs/backend changed')
        report=json.loads(Path('reviewed/caps-plan-review.json').read_text())
        require(hashlib.sha256(Path('reviewed/caps.tfplan').read_bytes()).hexdigest()==report['saved_plan_sha256']==os.environ.get('REVIEWED_DIGEST'),'Binary digest changed')
        require(plan_review(json.loads(Path('caps-plan.json').read_text()),config)=={k:v for k,v in report.items() if k!='saved_plan_sha256'},'Saved policy scope changed')
    else:
        authorization(aws)
        identity=aws('sts','get-caller-identity')
        require(identity.get('Account')==ACCOUNT and identity.get('Arn','').startswith(
            f'arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/'), 'Wrong publisher verification session')
        proof=[verify_policy(name,config) for name in sorted(NAMES)]
        Path('caps-verification.json').write_text(json.dumps(dict(verified=True,policies=proof,no_role_mutations=True),indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('policy_review_json='+json.dumps([dict(arn=p['arn'],sha256=p['sha256']) for p in proof],separators=(',',':'))+'\n')
