"""Consistent JVM/container limits and a conservative host-memory preflight."""
from pathlib import Path
MIB=1024**2
MIN_MB=4096
MAX_MB=65536
JAVA_RESERVE_MB=2048

def limits(configuration):
    container=configuration.get('container_memory_mb',8192)
    heap=configuration.get('memory_mb',6144)
    if type(container) is not int or not MIN_MB<=container<=MAX_MB or container%1024:
        raise ValueError('invalid_container_memory_budget')
    if type(heap) is not int or not 1024<=heap<=container-JAVA_RESERVE_MB:
        raise ValueError('invalid_memory_budget')
    return container,heap

def host_memory(path=Path('/proc/meminfo')):
    values={line.split(':',1)[0]:int(line.split()[1])*1024 for line in path.read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
    if not values.get('MemTotal') or 'MemAvailable' not in values:raise ValueError('host_memory_unavailable')
    return values

def forecast(configuration,host,used=0):
    container,heap=limits(configuration);total,available=host['MemTotal'],host['MemAvailable']
    reserve=max(2*1024**3,total//10);reclaim=max(0,used) if type(used) is int else 0
    maximum=max(0,min(total-reserve,available+reclaim-reserve))
    return {'container_memory_mb':container,'java_memory_mb':heap,'host_total_mb':total//MIB,'host_available_mb':available//MIB,
            'host_reserve_mb':reserve//MIB,'maximum_mb':min(MAX_MB,maximum//(1024*MIB)*1024),'sufficient':container*MIB<=maximum}

def require(configuration,host,used=0):
    result=forecast(configuration,host,used)
    if not result['sufficient']:raise ValueError('insufficient_host_memory')
    return result
