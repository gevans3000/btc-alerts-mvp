import importlib.util
from pathlib import Path


def _load_module():
    path = Path('scripts/pid-129/dashboard_server.py')
    spec = importlib.util.spec_from_file_location('dashboard_server', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_dashboard_payload_has_flow_and_derivative_keys():
    mod = _load_module()
    data = mod.get_dashboard_data()
    assert 'flows' in data
    assert 'derivatives' in data
    assert isinstance(data['flows'], dict)
    assert isinstance(data['derivatives'], dict)


def test_dashboard_payload_has_profit_preflight_block():
    mod = _load_module()
    data = mod.get_dashboard_data()
    assert 'profit_preflight' in data
    pf = data['profit_preflight']
    assert isinstance(pf, dict)
    assert 'ready' in pf
    assert 'checks' in pf
    assert isinstance(pf['checks'], list)
