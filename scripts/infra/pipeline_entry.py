"""Validate the deployment entry and bind stages to actual same-run interfaces.

No AWS changes, Terraform state writes or GitHub variable writes occur here.
"""
import argparse
import json
import os
from pathlib import Path
from iam_contract import ACCOUNT, REGION, require


def entry(env):
    require(env.get('GITHUB_REPOSITORY') == 'mhachem110/BankingReleasePlatform-AWS-EKS'
            and env.get('GITHUB_REF') == 'refs/heads/dev'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'Deploy only reviewed dev; PR CI cannot obtain AWS access')
    require(env.get('AWS_OPERATIONS_ENABLED') == 'true' and env.get('CLEANUP_ENABLED') != 'true',
            'Creation must be enabled and cleanup disabled')
    require(env.get('OPERATION') in {'plan', 'apply'}, 'No destruction or state repair in Infra CI/CD')
    require(env.get('TARGET') in {'project', 'foundation', 'network', 'platform', 'data'}, 'Unknown deployment target')
    if env['OPERATION'] == 'apply':
        require(env.get('APPROVAL') == 'APPLY-REVIEWED-BANKING-PROJECT', 'Apply requires the project phrase and native saved-plan reviews')
    return dict(target=env['TARGET'], operation=env['OPERATION'])


def platform_bindings(env):
    foundation = json.loads(env.get('FOUNDATION_INTERFACE_JSON') or '{}')
    network = json.loads(env.get('NETWORK_INTERFACE_JSON') or '{}')
    values = json.loads(env.get('PLATFORM_INPUTS_JSON') or '{}')
    if foundation:
        require(foundation.get('verified') is True, 'Foundation is planned but not verified; apply the reviewed dependency first')
        for key in ['kms_key_arn', 'operator_role_arn']:
            require(foundation.get(key), 'Missing actual foundation output: ' + key)
            values[key] = foundation[key]
    if network:
        require(network.get('verified') is True and network.get('account') == ACCOUNT and network.get('region') == REGION,
                'Network dependency has not been verified in the project account and Region')
    return values, network


def data_bindings(env):
    foundation = json.loads(env.get('FOUNDATION_INTERFACE_JSON') or '{}')
    platform = json.loads(env.get('PLATFORM_INTERFACE_JSON') or '{}')
    values = json.loads(env.get('DATA_INPUTS_JSON') or '{}')
    if foundation:
        require(foundation.get('verified') is True and foundation.get('kms_key_arn'), 'Verified foundation key required')
        values['kms_key_arn'] = foundation['kms_key_arn']
    if platform:
        require(platform.get('verified') is True, 'Verified platform outputs required before data creation')
        for key in ['vpc_id', 'database_subnet_ids', 'cluster_security_group_id']:
            require(platform.get('outputs', {}).get(key, {}).get('value'), 'Missing actual platform output: ' + key)
            values[key] = platform['outputs'][key]['value']
    return values


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=['entry', 'platform-bindings', 'data-bindings']); args = parser.parse_args()
    if args.command == 'entry':
        Path('pipeline-entry.json').write_text(json.dumps(entry(os.environ), indent=2))
    elif args.command == 'platform-bindings':
        values, network = platform_bindings(os.environ)
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as out:
            out.write('PLATFORM_INPUTS_JSON=' + json.dumps(values, separators=(',', ':')) + '\n')
            if network:out.write('NETWORK_SEED_REVIEW_JSON=' + json.dumps(network, separators=(',', ':')) + '\n')
    else:
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as out:
            out.write('DATA_INPUTS_JSON=' + json.dumps(data_bindings(os.environ), separators=(',', ':')) + '\n')
