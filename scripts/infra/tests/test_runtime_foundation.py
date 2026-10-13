import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/infra'))
import runtime_foundation as f
import cleanup_guard as c


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run=subprocess.run(['terraform','-chdir=infra/runtime-foundation','test','-json','-verbose'],cwd=ROOT,capture_output=True,text=True,check=True,timeout=90)
        plan=next(json.loads(s)['test_plan'] for s in run.stdout.splitlines() if json.loads(s).get('type')=='test_plan')
        cls.plan=dict(resource_changes=plan['resource_changes'],applyable=True,complete=True)

    def test_actual_mock_plan_has_only_new_project_key_and_operator(self):
        self.assertEqual(f.plan_review(self.plan,False)['managed_creates'],5)
        for cap in [f.session_policy(),f.session_policy(True)]:self.assertLessEqual(len(cap),2048)
        writer=json.loads(f.session_policy(True))
        iam=[r for r in writer['Statement'] if 'iam:CreateRole' in str(r['Action'])]
        self.assertEqual([r['Resource'] for r in iam],[f.OPERATOR])
        self.assertNotIn('iam:AttachRolePolicy',json.dumps(writer))

    def test_plan_rejects_operator_escalation_key_policy_drift_and_mutations(self):
        for issue in ['admin-policy','wrong-trust','shared-key','replacement','extra']:
            plan=copy.deepcopy(self.plan)
            by={r['address']:r for r in plan['resource_changes']}
            if issue=='admin-policy':by['aws_iam_role_policy.operator']['change']['after']['policy']='{"Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
            if issue=='wrong-trust':by['aws_iam_role.operator']['change']['after']['assume_role_policy']='{}'
            if issue=='shared-key':by['aws_kms_key.runtime']['change']['after']['policy']='{}'
            if issue=='replacement':by['aws_kms_key.runtime']['change']['actions']=['delete','create']
            if issue=='extra':plan['resource_changes'].append(dict(by['aws_iam_role.operator'],address='aws_iam_role.bootstrap'))
            with self.subTest(issue=issue),self.assertRaises(ValueError):f.plan_review(plan,False)

    def test_existing_operator_is_not_adopted_and_access_denial_is_not_absence(self):
        def call(service,operation,*args,**kwargs):
            if operation=='get-caller-identity':return dict(Account=f.ACCOUNT,Arn=f'arn:aws:sts::{f.ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/test')
            if operation=='get-role':return dict(Role={'Arn':f.OPERATOR})
            raise AssertionError(operation)
        with patch('runtime_foundation.verify_authorization'),self.assertRaisesRegex(ValueError,'already exists'):f.preflight(call)

    def cleanup_fixture(self):
        key_id='01234567-0123-0123-0123-0123456789ab'; key=f'arn:aws:kms:{f.REGION}:{f.ACCOUNT}:key/{key_id}'
        config=dict(target='runtime-foundation',key=f.KEY)
        resources=[('terraform_data','authorization',dict(id='local')),
                   ('aws_kms_key','runtime',dict(id=key_id,arn=key,policy=json.dumps(f.document('key-policy')),deletion_window_in_days=7,tags=dict(f.TAGS,Name='banking-runtime'))),
                   ('aws_kms_alias','runtime',dict(id=f.ALIAS,name=f.ALIAS,arn=f'arn:aws:kms:{f.REGION}:{f.ACCOUNT}:{f.ALIAS}',target_key_id=key_id)),
                   ('aws_iam_role','operator',dict(id=f.OPERATOR.split('/')[-1],arn=f.OPERATOR,assume_role_policy=json.dumps(f.document('operator-trust')),tags=dict(f.TAGS,Name=f.OPERATOR.split('/')[-1]))),
                   ('aws_iam_role_policy','operator',dict(id='inline',name='BankingOperator',role=f.OPERATOR.split('/')[-1],policy=json.dumps(f.document('operator-policy'))))]
        state=dict(lineage='fixture-lineage',serial=1,resources=[dict(mode='managed',type=t,name=n,instances=[dict(attributes=v)]) for t,n,v in resources])
        return config,c.state_review(state,config,{}),state

    def test_foundation_cleanup_cap_schedules_only_actual_project_key(self):
        config,report,state=self.cleanup_fixture();cap=c.foundation_delete_cap(config,report)
        self.assertLessEqual(len(cap),2048)
        rows=json.loads(cap)['Statement'];key=next(r for r in rows if r['Action']=='kms:ScheduleKeyDeletion')
        self.assertEqual(key['Resource'],state['resources'][1]['instances'][0]['attributes']['arn'])
        self.assertEqual(key['Condition']['StringEquals']['aws:ResourceTag/Name'],'banking-runtime')
        self.assertEqual(next(r for r in rows if r['Action']=='kms:DeleteAlias')['Resource'],state['resources'][2]['instances'][0]['attributes']['arn'])
        self.assertNotIn('kms:PutKeyPolicy',cap)
        changed=copy.deepcopy(state);changed['resources'][1]['instances'][0]['attributes']['tags']['Name']='shared-key'
        with self.assertRaises(ValueError):c.state_review(changed,config,{})

    def test_key_cleanup_stops_on_grants_cluster_access_or_retained_encrypted_resources(self):
        config,report,state=self.cleanup_fixture();values=state['resources'][1]['instances'][0]['attributes'];arn=values['arn'];role=state['resources'][3]['instances'][0]['attributes']
        for issue in [None,'access','grant','snapshot','logs','queue']:
            def call(service,operation,*args,**kwargs):
                if operation=='list-clusters':return dict(clusters=['existing'])
                if operation=='list-access-entries':return dict(accessEntries=[f.OPERATOR] if issue=='access' else [])
                if operation=='describe-cluster':return dict(cluster=dict(encryptionConfig=[]))
                if operation=='get-role':return dict(Role=dict(Arn=f.OPERATOR,Path='/',AssumeRolePolicyDocument=f.document('operator-trust'),Tags=[dict(Key=k,Value=v) for k,v in role['tags'].items()]))
                if operation=='list-attached-role-policies':return dict(AttachedPolicies=[])
                if operation=='list-instance-profiles-for-role':return dict(InstanceProfiles=[])
                if operation=='list-role-policies':return dict(PolicyNames=['BankingOperator'])
                if operation=='get-role-policy':return dict(PolicyDocument=f.document('operator-policy'))
                if operation=='describe-key':return dict(KeyMetadata=dict(Arn=arn,KeyId=values['id'],KeyState='Enabled',KeySpec='SYMMETRIC_DEFAULT',KeyUsage='ENCRYPT_DECRYPT'))
                if operation=='get-key-policy':return dict(Policy=json.dumps(f.document('key-policy')))
                if operation=='list-resource-tags':return dict(Tags=[dict(TagKey=k,TagValue=v) for k,v in values['tags'].items()])
                if operation=='list-grants':return dict(Grants=[{}] if issue=='grant' else [])
                if operation=='list-aliases':return dict(Aliases=[dict(AliasName=f.ALIAS)])
                if operation=='describe-db-instances':return dict(DBInstances=[])
                if operation=='describe-db-snapshots':return dict(DBSnapshots=[dict(KmsKeyId=arn)] if issue=='snapshot' else [])
                if operation=='describe-volumes':return dict(Volumes=[])
                if operation=='describe-log-groups':return dict(logGroups=[dict(kmsKeyId=arn)] if issue=='logs' else [])
                if operation=='list-queues':return dict(QueueUrls=['fixture-queue'])
                if operation=='get-queue-attributes':return dict(Attributes=dict(KmsMasterKeyId=arn) if issue=='queue' else {})
                raise AssertionError(operation)
            with self.subTest(issue=issue),patch('cleanup_guard.other_state_empty'),patch('cleanup_guard.aws',side_effect=call):
                if issue is None:c.foundation_preflight(report)
                else:
                    with self.assertRaises(ValueError):c.foundation_preflight(report)


if __name__=='__main__':unittest.main()
