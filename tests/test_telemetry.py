import copy
import pytest
from mcj.telemetry import normalized_cpu

STATS = {'cpu_stats': {'cpu_usage': {'total_usage': 200}, 'system_cpu_usage': 1700, 'online_cpus': 16},
         'precpu_stats': {'cpu_usage': {'total_usage': 100}, 'system_cpu_usage': 100}}


@pytest.mark.parametrize('limits,capacity,expected', [
    ({}, 16, 6.25), ({'NanoCpus': 4_000_000_000}, 4, 25),
    ({'CpuQuota': 200_000, 'CpuPeriod': 100_000}, 2, 50),
    ({'CpusetCpus': '0-1'}, 2, 50), ({'CpusetCpus': '0,2,4-5'}, 4, 25),
    ({'NanoCpus': 4_000_000_000, 'CpusetCpus': '0-1'}, 2, 50),
    ({'CpuQuota': 50_000, 'CpuPeriod': 100_000}, .5, 100),
    ({'CpuQuota': -1, 'CpuPeriod': 100_000}, 16, 6.25),
])
def test_cpu_uses_actual_allowed_capacity(limits, capacity, expected):
    assert normalized_cpu(STATS, limits) == {'cpu_capacity': capacity, 'cpu_normalized_percent': expected}


@pytest.mark.parametrize('field,value', [('online_cpus', None), ('online_cpus', 0),
    ('system_cpu_usage', None), ('system_cpu_usage', 100)])
def test_missing_or_nonadvancing_samples_neutral(field, value):
    stats = copy.deepcopy(STATS)
    stats['cpu_stats'][field] = value
    assert normalized_cpu(stats, {})['cpu_normalized_percent'] is None


@pytest.mark.parametrize('value', ['bad', '1-0', '0-5000', '0,,1'])
def test_invalid_cpu_set_not_invented(value):
    assert normalized_cpu(STATS, {'CpusetCpus': value})['cpu_normalized_percent'] is None
