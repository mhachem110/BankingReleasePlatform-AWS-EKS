import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/infra'))
from iam_contract import ACCOUNT
from network_seed import ADDRESSES, inputs, plan_review, state_vpc, verify_seed, session_policy, creation_probe, existing_seed
from test_safety import fixture


class SeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(['terraform', '-chdir=infra/network-seed', 'test', '-json', '-verbose'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
        plan = next(json.loads(line)['test_plan'] for line in run.stdout.splitlines() if json.loads(line).get('type') == 'test_plan' and json.loads(line).get('@testrun') == 'vpc_without_iam_or_kms')
        cls.plan = dict(resource_changes=plan['resource_changes'], applyable=True, complete=True)
        cls.values = inputs(dict(fixture(), NETWORK_SEED_ENABLED='true'))
        cls.info = dict(account=ACCOUNT, region='us-east-2', state_key='banking-release-platform/dev/platform/terraform.tfstate', vpc_id='vpc-0123456789abcdef0', default_security_group_id='sg-0123456789abcdef0')
        cls.env = dict(NETWORK_SEED_REVIEW_JSON=json.dumps(cls.info))
        cls.tags = next(r for r in cls.plan['resource_changes'] if r['type'] == 'aws_vpc')['change']['after']['tags']

    def state(self):
        return dict(resources=[dict(mode='managed', type='terraform_data', name='prerequisites', instances=[dict(attributes={})]), dict(mode='managed', module='module.network', type='aws_vpc', name='this', instances=[dict(attributes=dict(id=self.info['vpc_id'], default_security_group_id=self.info['default_security_group_id'], cidr_block='10.70.0.0/16', tags=self.tags))])])

    def call(self, service, operation, *args):
        self.assertEqual(service, 'ec2')
        if operation == 'describe-vpcs':
            return dict(Vpcs=[dict(VpcId=self.info['vpc_id'], CidrBlock='10.70.0.0/16', OwnerId=ACCOUNT, Tags=[dict(Key=k, Value=v) for k, v in self.tags.items()])])
        self.assertEqual(operation, 'describe-security-groups')
        return dict(SecurityGroups=[dict(GroupId=self.info['default_security_group_id'], VpcId=self.info['vpc_id'], GroupName='default', OwnerId=ACCOUNT)])

    def test_independent_mock_plan_has_only_one_aws_vpc(self):
        result = plan_review(self.plan, self.values, effective_tags=False)
        self.assertEqual(result['inventory'], sorted(ADDRESSES))
        self.assertEqual(result['aws_vpcs'], 1)
        with self.assertRaisesRegex(ValueError, 'tags'):
            plan_review(self.plan, self.values)

    def test_seed_cannot_add_nat_eks_iam_or_adopt_existing_resources(self):
        for change in ('extra', 'update', 'import', 'cidr', 'tags'):
            plan = copy.deepcopy(self.plan)
            row = next(r for r in plan['resource_changes'] if r['type'] == 'aws_vpc')
            if change == 'extra': plan['resource_changes'].append(dict(row, address='module.eks.aws_eks_cluster.this', type='aws_eks_cluster'))
            if change == 'update': row['change']['actions'] = ['update']
            if change == 'import': row['change']['importing'] = dict(id=self.info['vpc_id'])
            if change == 'cidr': row['change']['after']['cidr_block'] = '10.20.0.0/16'
            if change == 'tags': row['change']['after']['tags']['Project'] = 'Retail'
            with self.subTest(change=change), self.assertRaises(ValueError): plan_review(plan, self.values, False)

    def test_only_verified_state_and_actual_default_group_are_accepted(self):
        self.assertEqual(verify_seed(self.env, self.values, self.state(), self.call), self.info)
        for mutation in ('state_id', 'state_tags', 'extra_state', 'wrong_live_group'):
            state = self.state(); call = self.call
            if mutation == 'state_id': state['resources'][1]['instances'][0]['attributes']['id'] = 'vpc-aaaaaaaaaaaaaaaaa'
            if mutation == 'state_tags': state['resources'][1]['instances'][0]['attributes']['tags'] = dict(self.tags, Project='Retail')
            if mutation == 'extra_state': state['resources'].append(dict(mode='managed', type='aws_iam_role', name='other', instances=[{}]))
            if mutation == 'wrong_live_group':
                def call(service, operation, *args):
                    result = self.call(service, operation, *args)
                    if operation == 'describe-security-groups': result['SecurityGroups'][0]['VpcId'] = 'vpc-aaaaaaaaaaaaaaaaa'
                    return result
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): verify_seed(self.env, self.values, state, call)

    def test_seed_needs_its_own_gate_and_apply_approval(self):
        with self.assertRaises(ValueError): inputs(fixture())
        with self.assertRaises(ValueError): inputs(dict(fixture(), NETWORK_SEED_ENABLED='true', OPERATION='apply', APPROVAL='APPLY-REVIEWED-PHASE3-PLAN'))
        inputs(dict(fixture(), NETWORK_SEED_ENABLED='true', OPERATION='apply', APPROVAL='APPLY-REVIEWED-BANKING-VPC-SEED'))

    def test_seed_session_cannot_create_security_groups_or_paid_resources(self):
        cap = session_policy()
        self.assertLessEqual(len(cap), 2048)
        actions = {a for row in json.loads(cap)['Statement'] for a in (row['Action'] if isinstance(row['Action'], list) else [row['Action']])}
        self.assertIn('ec2:CreateVpc', actions)
        self.assertFalse(actions & {'ec2:CreateSecurityGroup', 'ec2:CreateNatGateway', 'eks:CreateCluster', 'iam:CreateRole', 'rds:CreateDBInstance', 'ec2:DeleteVpc'})
        self.assertFalse(any(a.startswith(('iam:', 'kms:')) for a in actions))

    def test_read_session_cannot_create_modify_or_write_native_state(self):
        cap=json.loads(session_policy(False))
        actions={a for r in cap['Statement'] for a in (r['Action'] if isinstance(r['Action'],list) else [r['Action']])}
        self.assertFalse(actions & {'ec2:CreateVpc','ec2:CreateTags','ec2:ModifyVpcAttribute'})
        state=next(r for r in cap['Statement'] if r['Resource'].endswith('/terraform.tfstate'))
        self.assertEqual(state['Action'],['s3:GetObject'])

    def test_existing_seed_reuses_native_ids_and_never_plans_seed_root_over_full_platform(self):
        def call(service,operation,*args):
            if operation=='describe-vpc-attribute':
                key='EnableDnsSupport' if args[-1]=='enableDnsSupport' else 'EnableDnsHostnames'
                return {key:{'Value':True}}
            return self.call(service,operation,*args)
        self.assertIsNone(existing_seed({},self.values,call))
        state=self.state()
        # Additional known platform state is retained; only the VPC is read here.
        state['resources'].append(dict(mode='managed',module='module.eks',type='aws_eks_cluster',name='this',instances=[dict(attributes={'id':'banking-dev'})]))
        result=existing_seed(state,self.values,call)
        self.assertTrue(result['verified']);self.assertEqual(result['vpc_id'],self.info['vpc_id'])
        state['resources'][-1]['name']='retail'
        with self.assertRaises(ValueError):existing_seed(state,self.values,call)
        with self.assertRaises(ValueError):existing_seed(dict(resources=[self.state()['resources'][0]]),self.values,call)

    def test_workflow_preserves_two_reviews_and_exact_binary(self):
        source = (ROOT / '.github/workflows/network-prerequisites.yml').read_text()
        self.assertEqual(source.count('environment: bootstrap'), 2)
        for text in ('APPLY-REVIEWED-BANKING-VPC-SEED', 'sha256sum --check --strict', 'cmp seed-policy-review.json reviewed/seed-policy-review.json', 'root=infra/network-seed', 'inline-session-policy:', 'network_seed.py verify'):
            self.assertIn(text, source)
        self.assertNotIn('-target=', source)
        self.assertNotIn('managed-session-policies:', source)

    def test_vpc_inputs_do_not_require_iam_key_or_access_roles(self):
        minimal = {k: v for k, v in fixture().items() if k in {'GITHUB_REF', 'AWS_OPERATIONS_ENABLED', 'BOOTSTRAP_STATE_READY', 'ROLE_ARN', 'AWS_REGION', 'AWS_EXPECTED_ACCOUNT_ID', 'TF_STATE_BUCKET', 'OPERATION'}}
        actual = inputs(dict(minimal, NETWORK_SEED_ENABLED='true'))
        self.assertEqual(actual['vpc_cidr'], '10.70.0.0/16')
        for field in ('kms_key_arn', 'operator_role_arn', 'iam_boundary_policy_sha256'):
            self.assertNotIn(field, actual)
        with self.assertRaises(ValueError):
            inputs(dict(minimal, NETWORK_SEED_ENABLED='true', VPC_SEED_INPUTS_JSON=json.dumps({'kms_key_arn': 'anything'})))

    def test_cap_cannot_delete_state_or_modify_an_untagged_vpc(self):
        cap = json.loads(session_policy())
        delete = next(row for row in cap['Statement'] if 's3:DeleteObject' in row.get('Action', []))
        self.assertTrue(delete['Resource'].endswith('.tflock'))
        modify = next(row for row in cap['Statement'] if row['Action'] == 'ec2:ModifyVpcAttribute')
        self.assertEqual(modify['Condition']['StringEquals']['aws:ResourceTag/Name'], 'banking-dev-vpc')

    def test_seed_vpc_address_and_configuration_match_full_platform(self):
        # Compare actual HCL VPC attributes, not an invented state migration.
        from pathlib import Path
        import re
        sources = [(ROOT / path).read_text() for path in ['infra/modules/network/main.tf', 'infra/modules/vpc-seed/main.tf']]
        bodies = [re.search(r'resource "aws_vpc" "this" \{(.*?)\n\}', source, re.S).group(1) for source in sources]
        for attribute in ('cidr_block', 'enable_dns_support', 'enable_dns_hostnames', 'tags'):
            rows = [next(line.strip() for line in body.splitlines() if line.strip().startswith(attribute + ' ')) for body in bodies]
            self.assertEqual(rows[0], rows[1])

    def test_authorization_probe_always_dry_runs_and_retains_aws_denials(self):
        def allowed(command, **options):
            self.assertIn('--dry-run', command)
            self.assertEqual(command[0:3], ['aws', 'ec2', 'create-vpc'])
            return subprocess.CompletedProcess(command, 255, '', 'An error occurred (DryRunOperation): Request would have succeeded')
        self.assertTrue(creation_probe(self.values, allowed)['authorized'])
        for error in ('UnauthorizedOperation', 'AccessDenied', 'VpcLimitExceeded'):
            def denied(command, **options):
                return subprocess.CompletedProcess(command, 255, '', 'An error occurred (' + error + ')')
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                creation_probe(self.values, denied)


if __name__ == '__main__':
    unittest.main()
