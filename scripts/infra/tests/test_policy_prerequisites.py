import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/infra'))
from policy_prerequisites import configuration, plan_review, session_policy, POLICIES
import bootstrap_authorization
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, digest


class PolicyPublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(['terraform', '-chdir=infra/policy-prerequisites', 'test', '-json', '-verbose'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
        plan = next(json.loads(line)['test_plan'] for line in run.stdout.splitlines() if json.loads(line).get('type') == 'test_plan')
        cls.plan = dict(resource_changes=plan['resource_changes'], applyable=True, complete=True)

    def test_actual_mock_plan_only_publishes_two_exact_documents(self):
        self.assertEqual(plan_review(self.plan, effective_tags=False)['managed_creates'], 3)
        with self.assertRaisesRegex(ValueError, 'tags'):
            plan_review(self.plan)

    def test_policy_escalation_role_mutation_and_unreviewed_update_are_rejected(self):
        for mutation in ['name', 'path', 'policy', 'tags', 'extra', 'update', 'import']:
            plan = copy.deepcopy(self.plan)
            row = next(r for r in plan['resource_changes'] if r['type'] == 'aws_iam_policy'); value = row['change']['after']
            if mutation == 'name': value['name'] = 'AdministratorAccess'
            if mutation == 'path': value['path'] = '/other/'
            if mutation == 'policy': value['policy'] = json.dumps(dict(Version='2012-10-17', Statement=[dict(Effect='Allow', Action='*', Resource='*')]))
            if mutation == 'tags': value['tags']['Project'] = 'Retail'
            if mutation == 'extra': plan['resource_changes'].append(dict(row, address='aws_iam_role.bootstrap', type='aws_iam_role'))
            if mutation == 'update': row['change']['actions'] = ['update']
            if mutation == 'import': row['change']['importing'] = dict(id='existing')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): plan_review(plan, effective_tags=False)

    def test_write_session_cannot_attach_policies_or_mutate_roles(self):
        for write in [False, True]:
            cap = session_policy(write); self.assertLessEqual(len(cap), 2048)
            rows = json.loads(cap)['Statement']
            writes = [r for r in rows if any(a.startswith(('iam:Create', 'iam:Tag', 'iam:Attach', 'iam:Put', 'iam:Update', 'iam:Delete')) for a in r['Action'])]
            self.assertEqual(len(writes), int(write))
            if write:
                self.assertEqual(set(writes[0]['Action']), {'iam:CreatePolicy', 'iam:TagPolicy'})
                self.assertEqual(set(writes[0]['Resource']), {v[0] for v in POLICIES.values()})

    def test_creation_window_rejects_cleanup_or_wrong_role(self):
        env = dict(GITHUB_REPOSITORY='mhachem110/BankingReleasePlatform-AWS-EKS', GITHUB_REF='refs/heads/dev', POLICY_PUBLISH_ENABLED='true', AWS_OPERATIONS_ENABLED='true', CLEANUP_ENABLED='false', BOOTSTRAP_STATE_READY='true', ROLE_ARN=BOOTSTRAP, AWS_EXPECTED_ACCOUNT_ID=ACCOUNT, AWS_REGION=REGION, TF_STATE_BUCKET=BUCKET, OPERATION='plan')
        configuration(env)
        for change in [dict(CLEANUP_ENABLED='true'), dict(ROLE_ARN='other'), dict(GITHUB_REF='refs/heads/infra'), dict(OPERATION='apply', APPROVAL='')]:
            with self.subTest(change=change), self.assertRaises(ValueError): configuration(dict(env, **change))


class OwnerAuthorizationTests(unittest.TestCase):
    def test_owner_configuration_drift_stops_without_an_iam_write(self):
        trust = dict(Version='2012-10-17', Statement=[])
        grant = dict(Version='2012-10-17', Statement=[dict(Effect='Allow', Action='ec2:DescribeVpcs', Resource='*')])
        responses = {'get-role': dict(Role=dict(Arn=BOOTSTRAP, AssumeRolePolicyDocument=trust)), 'list-role-policies': dict(PolicyNames=['terraform-policy']), 'get-role-policy': dict(PolicyDocument=grant), 'list-attached-role-policies': dict(AttachedPolicies=[])}
        def call(service, operation, *args):
            self.assertEqual(service, 'iam'); self.assertIn(operation, responses); return responses[operation]
        with patch.object(bootstrap_authorization, 'TRUST_SHA256', digest(trust)), patch.object(bootstrap_authorization, 'POLICY_SHA256', digest(grant)):
            bootstrap_authorization.verify(call)
            responses['list-attached-role-policies']['AttachedPolicies'] = [dict(PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess')]
            with self.assertRaisesRegex(ValueError, 'attached-policy'): bootstrap_authorization.verify(call)
            responses['list-attached-role-policies']['AttachedPolicies'] = []
            grant['Statement'].append(dict(Effect='Allow', Action='*', Resource='*'))
            with self.assertRaisesRegex(ValueError, 'grant changed'): bootstrap_authorization.verify(call)


if __name__ == '__main__':
    unittest.main()
