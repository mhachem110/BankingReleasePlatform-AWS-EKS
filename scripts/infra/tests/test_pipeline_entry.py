import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts/infra'))
from pipeline_entry import entry, platform_bindings, data_bindings
from iam_contract import ACCOUNT, REGION


class PipelineTests(unittest.TestCase):
    def test_dispatch_requires_owner_scope_and_separates_creation_from_cleanup(self):
        env = dict(GITHUB_REPOSITORY='mhachem110/BankingReleasePlatform-AWS-EKS',
            GITHUB_REF='refs/heads/dev', GITHUB_EVENT_NAME='workflow_dispatch',
            AWS_OPERATIONS_ENABLED='true', CLEANUP_ENABLED='false',
            OPERATION='apply', TARGET='project', APPROVAL='APPLY-REVIEWED-BANKING-PROJECT')
        self.assertEqual(entry(env)['target'], 'project')
        for change in [dict(GITHUB_REF='refs/heads/infra'), dict(GITHUB_EVENT_NAME='pull_request'),
                dict(CLEANUP_ENABLED='true'),dict(AWS_OPERATIONS_ENABLED='false'),dict(OPERATION='destroy'),
                dict(APPROVAL=''),dict(TARGET='another-account')]:
            with self.subTest(change=change),self.assertRaises(ValueError):entry(dict(env,**change))

    def test_actual_dependency_outputs_override_stale_console_ids(self):
        foundation = dict(verified=True,kms_key_arn='actual-key',operator_role_arn='actual-operator')
        network = dict(verified=True,account=ACCOUNT,region=REGION,vpc_id='actual-vpc')
        env = dict(FOUNDATION_INTERFACE_JSON=json.dumps(foundation),NETWORK_INTERFACE_JSON=json.dumps(network),
            PLATFORM_INPUTS_JSON=json.dumps(dict(kms_key_arn='stale',operator_role_arn='stale',endpoint_cidrs=['operator/32'])))
        values,seed=platform_bindings(env)
        self.assertEqual(values['kms_key_arn'],'actual-key');self.assertEqual(values['operator_role_arn'],'actual-operator')
        self.assertEqual(seed,network);self.assertEqual(values['endpoint_cidrs'],['operator/32'])
        for field,bad in [('FOUNDATION_INTERFACE_JSON',dict(foundation,verified=False)),
                ('NETWORK_INTERFACE_JSON',dict(network,account='another-account'))]:
            with self.subTest(field=field),self.assertRaises(ValueError):platform_bindings(dict(env,**{field:json.dumps(bad)}))

    def test_data_requires_verified_platform_and_keeps_owned_class_and_engine_settings(self):
        platform = dict(verified=True,outputs={k:dict(value=v) for k,v in dict(vpc_id='actual-vpc',
            database_subnet_ids=['actual-subnet-a','actual-subnet-b'],cluster_security_group_id='actual-sg').items()})
        env = dict(PLATFORM_INTERFACE_JSON=json.dumps(platform),DATA_INPUTS_JSON=json.dumps(dict(vpc_id='stale',engine_version='17.7',instance_class='db.t4g.micro')))
        values=data_bindings(env);self.assertEqual(values['vpc_id'],'actual-vpc');self.assertEqual(values['engine_version'],'17.7')
        with self.assertRaises(ValueError):data_bindings(dict(env,PLATFORM_INTERFACE_JSON=json.dumps(dict(platform,verified=False))))
        missing=dict(platform,outputs={})
        with self.assertRaises(ValueError):data_bindings(dict(env,PLATFORM_INTERFACE_JSON=json.dumps(missing)))


if __name__=='__main__':unittest.main()
