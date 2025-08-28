import datetime as dt
from typing import Dict, Any

import yaml


def load_funding_schedules(path: str = "/workspace/conf/funding_schedules.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def seconds_to_next_funding(exchange_key: str, now: dt.datetime = None, conf_path: str = "/workspace/conf/funding_schedules.yaml") -> float:
    now = now or dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    conf = load_funding_schedules(conf_path)
    ex = conf.get("exchanges", {}).get(exchange_key)
    if not ex:
        return float("nan")
    times = ex.get("times_utc", [])
    # Build today's and next day's funding times
    candidates = []
    for day_offset in [0, 1]:
        day = (now + dt.timedelta(days=day_offset)).date()
        for t in times:
            hh, mm = map(int, t.split(":"))
            dt_candidate = dt.datetime.combine(day, dt.time(hh, mm, tzinfo=dt.timezone.utc))
            candidates.append(dt_candidate)
    future = [c for c in candidates if c > now]
    if not future:
        return float("nan")
    delta = min(future) - now
    return delta.total_seconds()

