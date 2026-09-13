"""Species-type matchups, excluding abilities, items and battle state."""
from functools import lru_cache
from pathlib import Path
import json
from .paths import app_paths


@lru_cache(maxsize=1)
def chart():
    return json.loads(app_paths().resource('config/type_chart.json').read_text(encoding='utf-8'))


def type_matchups(types):
    table=chart()
    if not types or any(t not in table for t in types):return None
    result={'weakness':[], 'resistance':[], 'immune':[]}
    for attack,matchups in table.items():
        multiplier=1
        for defense in dict.fromkeys(types):multiplier*=matchups[defense]
        key='immune' if multiplier==0 else 'weakness' if multiplier>1 else 'resistance' if multiplier<1 else None
        if key:result[key].append((attack,multiplier))
    for rows in result.values():rows.sort(key=lambda v:-v[1])
    return result
