"""Keep persistent manager configuration separate from observed runtime evidence."""
FIELDS=('version','java','loader','loader_version')

def compare(database,runtime):
    if not isinstance(runtime,dict) or any(database.get(k) is None or runtime.get(k) is None for k in FIELDS):
        return {'state':'unverified','different_fields':[]}
    different=[key for key in FIELDS if database[key]!=runtime[key]]
    return {'state':'mismatch' if different else 'consistent','different_fields':different}
