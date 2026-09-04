from typing import Optional, Dict

_cache: Dict[str, Dict] = {}

def cache_get(key: str) -> Optional[Dict]:
    return _cache.get(key)

def cache_set(key: str, value: Dict) -> None:
    _cache[key] = value
