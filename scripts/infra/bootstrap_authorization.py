"""Pin the owner's live IAM configuration verified by run 38382778844.

The owner replaced the former inline/trust configuration in the IAM console.
This contract accepts that verified update without modifying the shared role.
Project session caps restrict the existing grant; they need no role attachment.
"""
from iam_contract import BOOTSTRAP, digest, require

POLICY_SHA256 = 'a303296355d2fa5ac5402f30f7ea902fcd67a57811bf7982688a8309c4e01552'
TRUST_SHA256 = '208ba6818c59e3763d82d4a5ffa71ec6960ec13e0643c072fa8f6df3dff0b4d2'


def verify(call):
    name = BOOTSTRAP.split('/')[-1]
    role = call('iam', 'get-role', '--role-name', name)['Role']
    require(role.get('Arn') == BOOTSTRAP and not role.get('PermissionsBoundary'), 'Bootstrap identity/boundary changed since owner review')
    require(digest(role['AssumeRolePolicyDocument']) == TRUST_SHA256, 'Owner-reviewed repository OIDC trust changed')
    inline = call('iam', 'list-role-policies', '--role-name', name)
    require(set(inline.get('PolicyNames', [])) == {'terraform-policy'}, 'Owner-reviewed inline policy inventory changed')
    document = call('iam', 'get-role-policy', '--role-name', name, '--policy-name', 'terraform-policy')['PolicyDocument']
    require(digest(document) == POLICY_SHA256, 'Owner-reviewed infrastructure grant changed')
    attached = call('iam', 'list-attached-role-policies', '--role-name', name)
    require(attached.get('AttachedPolicies') == [], 'Bootstrap attached-policy inventory changed')
    return dict(roleArn=BOOTSTRAP, policySha256=POLICY_SHA256, trustSha256=TRUST_SHA256,
                auditRun=38382778844, sessionCapsAreRoleAttachments=False)
