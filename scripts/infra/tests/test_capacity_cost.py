import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import unittest

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/infra' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capacity, cost = load('capacity-review'), load('cost-exposure')


class CapacityCostTests(unittest.TestCase):
    def test_recent_authorized_capacity(self):
        now = datetime.now(timezone.utc)
        data = dict(account='123456789012', region='us-east-2', reviewed_by='test-admin',
            observed_at=now.isoformat(), fargate_vcpu_limit=6, current_vcpu_usage=1,
            other_platform_limits_approved=True)
        self.assertEqual(capacity.verify(data, data['account'], now)['available_vcpu'], 5)
        for field, value in [('observed_at',(now-timedelta(days=2)).isoformat()),
            ('observed_at',(now+timedelta(hours=1)).isoformat()), ('region','us-east-1'),
            ('current_vcpu_usage',2), ('current_vcpu_usage',float('nan')),
            ('fargate_vcpu_limit',True), ('other_platform_limits_approved',False)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                capacity.verify(dict(data, **{field:value}), data['account'], now)

    def test_duration_and_scaling_model(self):
        model = json.loads((ROOT / 'docs/infrastructure/cost-model.json').read_text())
        result = cost.scenarios(model)
        self.assertEqual(result['initial_system']['duration_usd']['730'], '137.53')
        self.assertEqual(result['four_apis']['duration_usd']['730'], '180.06')
        self.assertEqual(result['hpa_max_all_rollouts']['steady_vcpu'], '4.50')
        self.assertEqual(result['hpa_max_all_rollouts']['pod_count'], 18)
        self.assertGreater(float(result['hpa_max']['hourly_usd']),float(result['four_apis']['hourly_usd']))

    def test_variable_usage_not_invented(self):
        self.assertEqual(cost.usage_estimate({})['total_usd'], '0.00')
        self.assertEqual(cost.usage_estimate({'nat_processed_gb':10})['total_usd'], '0.45')
        with self.assertRaises(ValueError):
            cost.usage_estimate({'new_paid_service':1})

