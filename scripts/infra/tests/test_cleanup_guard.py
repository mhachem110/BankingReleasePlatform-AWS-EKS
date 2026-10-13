import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/infra'))
from cleanup_guard import inputs, state_review, plan_review, preflight, read_policy, vpc_delete_cap, aws
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.seed = dict(account=ACCOUNT, region=REGION, state_key='banking-release-platform/dev/platform/terraform.tfstate', vpc_id='vpc-0123456789abcdef0', default_security_group_id='sg-0123456789abcdef0')
        self.env = dict(GITHUB_REPOSITORY='mhachem110/BankingReleasePlatform-AWS-EKS', GITHUB_REF='refs/heads/dev', CLEANUP_ENABLED='true', AWS_OPERATIONS_ENABLED='false', ROLE_ARN=BOOTSTRAP, AWS_EXPECTED_ACCOUNT_ID=ACCOUNT, AWS_REGION=REGION, TF_STATE_BUCKET=BUCKET, TARGET='vpc-seed', OPERATION='plan', GITHUB_RUN_ID='42', GITHUB_RUN_ATTEMPT='1', NETWORK_SEED_REVIEW_JSON=json.dumps(self.seed))
        self.config = inputs(self.env)
        self.state = dict(lineage='actual-lineage', serial=2, resources=[
            dict(mode='managed', type='terraform_data', name='prerequisites', instances=[dict(attributes=dict(id='local-id'))]),
            dict(mode='managed', module='module.network', type='aws_vpc', name='this', instances=[dict(attributes=dict(id=self.seed['vpc_id'], cidr_block='10.70.0.0/16', tags=dict(Project='BankingReleasePlatform', Environment='dev', ManagedBy='Terraform')))])])
        self.report = state_review(self.state, self.config, self.env)
        self.plan = dict(applyable=True, complete=True, resource_changes=[dict(mode='managed', address=r['address'], type=r['type'], change=dict(actions=['delete'], before=r['values'], after=None)) for r in self.report['inventory']])

    def test_cleanup_authorization_is_distinct_and_never_enables_creation(self):
        for change in [dict(AWS_OPERATIONS_ENABLED='true'), dict(CLEANUP_ENABLED='false'), dict(GITHUB_REF='refs/heads/infra'), dict(ROLE_ARN='arn:aws:iam::866934333672:role/other'), dict(TARGET='platform'), dict(OPERATION='apply', APPROVAL='')]:
            with self.subTest(change=change), self.assertRaises(ValueError): inputs(dict(self.env, **change))
        inputs(dict(self.env, OPERATION='apply', APPROVAL='DESTROY-REVIEWED-BANKING-VPC-SEED'))

    def test_wrong_resource_tag_id_type_or_unrelated_state_is_rejected(self):
        for mutation in ['id', 'tags', 'type', 'deposed', 'extra']:
            state = copy.deepcopy(self.state); resource = state['resources'][1]; value = resource['instances'][0]['attributes']
            if mutation == 'id': value['id'] = 'vpc-aaaaaaaaaaaaaaaaa'
            if mutation == 'tags': value['tags']['Project'] = 'Retail'
            if mutation == 'type': resource['type'] = 'aws_subnet'
            if mutation == 'deposed': resource['instances'][0]['deposed'] = 'old'
            if mutation == 'extra': state['resources'].append(dict(mode='managed', type='aws_iam_role', name='bootstrap', instances=[dict(attributes=dict(id='bootstrap'))]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): state_review(state, self.config, self.env)

    def test_destroy_plan_rejects_update_create_replacement_import_or_identity_drift(self):
        self.assertEqual(plan_review(self.plan, self.report)['managed_deletes'], 2)
        for mutation in ['update', 'create', 'replace', 'import', 'move', 'id', 'missing', 'incomplete']:
            plan = copy.deepcopy(self.plan); row = plan['resource_changes'][1]
            if mutation in {'update', 'create'}: row['change']['actions'] = [mutation]
            if mutation == 'replace': row['change']['actions'] = ['delete', 'create']
            if mutation == 'import': row['change']['importing'] = dict(id=self.seed['vpc_id'])
            if mutation == 'move': row['previous_address'] = 'aws_vpc.other'
            if mutation == 'id': row['change']['before']['id'] = 'vpc-aaaaaaaaaaaaaaaaa'
            if mutation == 'missing': plan['resource_changes'].pop()
            if mutation == 'incomplete': plan['complete'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): plan_review(plan, self.report)

    def test_inline_caps_fit_and_only_delete_verified_vpc_and_lock(self):
        for cap in [read_policy(self.config), vpc_delete_cap(self.config, self.env)]:
            self.assertLessEqual(len(cap), 2048)
        cap = json.loads(vpc_delete_cap(self.config, self.env))
        destructive = [r for r in cap['Statement'] if 'Delete' in str(r['Action'])]
        self.assertEqual(len(destructive), 2)
        vpc = next(r for r in destructive if r['Action'] == 'ec2:DeleteVpc')
        self.assertTrue(vpc['Resource'].endswith(self.seed['vpc_id']))
        self.assertEqual(vpc['Condition']['StringEquals']['aws:ResourceTag/Project'], 'BankingReleasePlatform')
        lock = next(r for r in destructive if isinstance(r['Action'], list))
        self.assertTrue(lock['Resource'].endswith('.tflock'))
        self.assertFalse(any('iam:Create' in str(r['Action']) or 'ec2:Create' in str(r['Action']) for r in cap['Statement']))

    def test_live_dependencies_block_vpc_deletion(self):
        def call(service, operation, *args, **kwargs):
            if service == 'ec2' and operation == 'describe-vpcs':
                return dict(Vpcs=[dict(OwnerId=ACCOUNT, CidrBlock='10.70.0.0/16', Tags=[dict(Key='Project', Value='BankingReleasePlatform')])])
            if operation == 'describe-subnets': return dict(Subnets=[dict(SubnetId='subnet-dependent')])
            raise AssertionError(operation)
        with patch('cleanup_guard.check_identity', return_value={}), patch('cleanup_guard.other_state_empty'), patch('cleanup_guard.aws', side_effect=call), self.assertRaisesRegex(ValueError, 'dependents'):
            preflight(self.config, self.report, self.env)

    def test_access_denied_is_not_resource_absence(self):
        import subprocess
        result = subprocess.CompletedProcess([], 255, '', 'An error occurred (AccessDenied): denied')
        with patch('cleanup_guard.subprocess.run', return_value=result), self.assertRaises(RuntimeError):
            aws('ec2', 'describe-vpcs', absent_codes=('InvalidVpcID.NotFound',))


if __name__ == '__main__':
    unittest.main()
