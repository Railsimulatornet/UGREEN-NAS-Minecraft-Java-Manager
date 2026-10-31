"""Presentation telemetry derived from actual Docker counters and CPU limits."""
import math
import threading
import copy


class DockerSamples:
    """Compare real counters without Docker's extra one-second sampling wait."""
    def __init__(self):
        self.lock=threading.Lock()
        self.identity=None
        self.previous=None

    def collect(self,container):
        from docker.errors import InvalidVersion
        with self.lock:
            try:stats=container.stats(stream=False,one_shot=True)
            except InvalidVersion:return container.stats(stream=False)
            identity=(container.id,container.attrs.get('State',{}).get('StartedAt'))
            stats['precpu_stats']=self.previous if identity==self.identity and self.previous else {}
            self.identity=identity
            self.previous=copy.deepcopy(stats.get('cpu_stats',{}))
            return stats


def normalized_cpu(stats, host):
    def number(value):
        return type(value) in (int, float) and math.isfinite(value)
    cpu, previous = stats.get('cpu_stats', {}), stats.get('precpu_stats', {})
    online = cpu.get('online_cpus')
    if not number(online) or online <= 0:
        return {'cpu_capacity': None, 'cpu_normalized_percent': None}
    limits = [float(online)]
    nano = host.get('NanoCpus')
    if number(nano) and nano > 0:
        limits.append(nano / 1_000_000_000)
    quota, period = host.get('CpuQuota'), host.get('CpuPeriod')
    if number(quota) and number(period) and quota > 0 and period > 0:
        limits.append(quota / period)
    cpuset = host.get('CpusetCpus')
    if cpuset:
        try:
            selected = set()
            for item in cpuset.split(','):
                bounds = [int(x) for x in item.split('-')]
                if len(bounds) == 1:
                    bounds *= 2
                if len(bounds) != 2 or not 0 <= bounds[0] <= bounds[1] < 4096:
                    raise ValueError()
                selected.update(range(bounds[0], bounds[1] + 1))
            if not selected:
                raise ValueError()
            limits.append(len(selected))
        except (ValueError, AttributeError):
            return {'cpu_capacity': None, 'cpu_normalized_percent': None}
    capacity = min(limits)
    counters = [cpu.get('cpu_usage', {}).get('total_usage'),
                previous.get('cpu_usage', {}).get('total_usage'),
                cpu.get('system_cpu_usage'), previous.get('system_cpu_usage')]
    if not all(number(x) for x in counters):
        return {'cpu_capacity': capacity, 'cpu_normalized_percent': None}
    usage, elapsed = counters[0] - counters[1], counters[2] - counters[3]
    if elapsed <= 0 or usage < 0:
        return {'cpu_capacity': capacity, 'cpu_normalized_percent': None}
    percent = usage / elapsed * online / capacity * 100
    return {'cpu_capacity': capacity, 'cpu_normalized_percent': round(min(100, max(0, percent)), 2)}
