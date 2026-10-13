import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/infra'))
import publish_platform_caps as p
import cleanup_guard as c


class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'infra/platform-caps/tests/fixtures.json').read_text())
        cls.config.pop('classification')
        run=subprocess.run(['terraform','-chdir=infra/platform-caps','test','-json','-verbose'],
            cwd=ROOT,capture_output=True,text=True,check=True,timeout=90)
        plan=next(json.loads(s)['test_plan'] for s in run.stdout.splitlines() if json.loads(s).get('type')=='test_plan')
        cls.plan=dict(resource_changes=plan['resource_changes'],applyable=True,complete=True)

    def test_actual_mock_plan_publishes_only_three_reproducible_caps(self):
        report=p.plan_review(self.plan,self.config,False)
        self.assertEqual(report['managed_creates'],4);self.assertEqual(report['role_mutations'],0)
        self.assertEqual(self.config['documents'],{name:p.canonical(doc) for name,doc in p.documents(self.config['bindings']).items()})
        for cap in [p.session_policy(),p.session_policy(True)]:self.assertLessEqual(len(cap),2048)
        writer=json.loads(p.session_policy(True))
        iam=[r for r in writer['Statement'] if 'iam:CreatePolicy' in str(r['Action'])]
        self.assertEqual(set(iam[0]['Resource']),set(p.ARNS.values()))
        self.assertNotIn('iam:AttachRolePolicy',p.session_policy(True))
        self.assertNotIn('iam:PutRolePolicy',p.session_policy(True))

    def test_plan_rejects_admin_document_wrong_binding_updates_and_extra_roles(self):
        for issue in ['policy','update','extra','name','tags']:
            plan=copy.deepcopy(self.plan);row=next(r for r in plan['resource_changes'] if r['type']=='aws_iam_policy')
            if issue=='policy':row['change']['after']['policy']='{"Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
            if issue=='update':row['change']['actions']=['update']
            if issue=='extra':plan['resource_changes'].append(dict(row,address='aws_iam_role.bootstrap',type='aws_iam_role'))
            if issue=='name':row['change']['after']['name']='AdministratorAccess'
            if issue=='tags':row['change']['after']['tags']['Project']='Retail'
            with self.subTest(issue=issue),self.assertRaises(ValueError):p.plan_review(plan,self.config,False)
        with self.assertRaises(ValueError):p.documents(dict(self.config['bindings'],operator_role_arn=p.BOOTSTRAP))

    def test_noop_plan_never_requests_an_apply(self):
        plan=copy.deepcopy(self.plan);plan['applyable']=False
        for row in plan['resource_changes']:row['change']['actions']=['no-op']
        self.assertEqual(p.plan_review(plan,self.config,False)['managed_creates'],0)

    def test_cleanup_removes_only_owned_source_caps_after_dependencies_are_empty(self):
        resources=[]
        for name,doc in self.config['documents'].items():
            resources.append(dict(mode='managed',type='aws_iam_policy',name='project',instances=[dict(index_key=name,
                attributes=dict(id=p.ARNS[name],arn=p.ARNS[name],name=name,path='/',policy=doc,tags=dict(p.TAGS,Name=name)))]))
        state=dict(lineage='mock',serial=1,resources=resources,outputs={k:dict(value=v) for k,v in
            dict(state_key=p.KEY,contract_version=1,bindings=self.config['bindings']).items()})
        config=dict(target='platform-caps',key=p.KEY)
        self.assertEqual(len(c.state_review(state,config,{})['inventory']),3)
        cap=c.policy_delete_cap(config);self.assertLessEqual(len(cap),2048)
        deletes=next(r for r in json.loads(cap)['Statement'] if r['Action']=='iam:DeletePolicy')
        self.assertEqual(set(deletes['Resource']),set(p.ARNS.values()))
        self.assertNotIn('iam:DeleteRole',cap)
        state['resources'][0]['instances'][0]['attributes']['policy']='{}'
        with self.assertRaises(ValueError):c.state_review(state,config,{})


if __name__=='__main__':unittest.main()
