"""Validate Prometheus config/rules and alert scenarios locally; no deployment or notifications."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT/'docs/deployment/monitoring'
PROMETHEUS = 'prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996'

if __name__ == '__main__':
    dashboard = json.loads((CONFIG/'grafana-dashboard.json').read_text())
    assert len(dashboard['panels']) == 9
    assert len({p['id'] for p in dashboard['panels']}) == 9
    for arguments in [
        ['check','config','/etc/prometheus/prometheus.yml'],
        ['check','rules','/etc/prometheus/alerts.yml'],
        ['test','rules','/etc/prometheus/alerts-test.yml']
    ]:
        result = subprocess.run(['docker','run','--rm','--network','none',
            '--mount',f'type=bind,source={CONFIG.resolve()},target=/etc/prometheus,readonly',
            '--entrypoint','/bin/promtool',PROMETHEUS,*arguments],text=True,capture_output=True)
        print(result.stdout, end='')
        if result.returncode:
            print(result.stderr)
            sys.exit(result.returncode)
    print('Monitoring configuration and sample alert evaluation passed; live dashboards/delivery remain pending.')
