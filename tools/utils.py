import yaml

def sanitize_for_ai(obj):
    """
    Recursively clean a Kubernetes object (dict) to remove fields that create
    massive token bloat but offer near-zero value for AI reasoning.
    """
    # If it's a list, process each element
    if isinstance(obj, list):
        return [sanitize_for_ai(item) for item in obj if item is not None]

    # If it's not a dict, return as is
    if not isinstance(obj, dict):
        # Handle k8s python objects with to_dict() method
        if hasattr(obj, 'to_dict'):
            return sanitize_for_ai(obj.to_dict())
        return obj

    cleaned = {}
    for k, v in obj.items():
        if v is None:
            continue

        # Skip bloat fields in metadata
        if k == 'metadata' and isinstance(v, dict):
            new_meta = {}
            for mk, mv in v.items():
                if mk in ['managedFields', 'resourceVersion', 'uid', 'generation', 'creationTimestamp', 'selfLink']:
                    continue
                if mk == 'annotations' and isinstance(mv, dict):
                    # Remove the massive last-applied-configuration dump
                    new_anno = {ak: av for ak, av in mv.items() if ak != 'kubectl.kubernetes.io/last-applied-configuration'}
                    if new_anno:
                        new_meta['annotations'] = new_anno
                else:
                    new_meta[mk] = sanitize_for_ai(mv)
            if new_meta:
                cleaned['metadata'] = new_meta
            continue
            
        # Clean nulls, empty lists/dicts deeply
        sanitized_val = sanitize_for_ai(v)
        if sanitized_val or sanitized_val in [False, 0]:  # keep valid zeroes and falses
            cleaned[k] = sanitized_val

    return cleaned

def to_compact_yaml(obj) -> str:
    """
    Convert a dictionary to a highly compact YAML string.
    YAML uses significantly fewer structural tokens than JSON.
    """
    if hasattr(obj, 'to_dict'):
        obj = obj.to_dict()
    sanitized = sanitize_for_ai(obj)
    return yaml.dump(sanitized, default_flow_style=False, sort_keys=False)

def truncate_logs(logs: str, max_chars: int = 3000) -> str:
    """
    Truncate logs to avoid context window blowup. Show the end of the logs primarily.
    """
    if not logs:
        return ""
    if len(logs) <= max_chars:
        return logs
    return f"[... TRUNCATED ...]\n{logs[-(max_chars):]}"
