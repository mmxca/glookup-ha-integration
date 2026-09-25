"""Parser tests. Run with: python -m pytest tests  (no Home Assistant needed)."""

import importlib.util
import json
import pathlib
import sys
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "glooko"

# Load const.py + parse.py as a lightweight package, skipping __init__.py (which imports HA).
pkg = types.ModuleType("glooko_pure")
pkg.__path__ = [str(ROOT)]
sys.modules["glooko_pure"] = pkg
for name in ("const", "parse"):
    spec = importlib.util.spec_from_file_location(f"glooko_pure.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"glooko_pure.{name}"] = mod
    spec.loader.exec_module(mod)
parse_mod = sys.modules["glooko_pure.parse"]

TZ = ZoneInfo("America/Chicago")
FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "synthetic.json").read_text())
NOW = datetime(2026, 1, 15, 8, 40, tzinfo=TZ)


def _parse(**over):
    args = dict(graph=FIX["graph"], devices=FIX["devices"], connections=FIX["connections"], stats=FIX["stats"], tz=TZ, now=NOW)
    args.update(over)
    return parse_mod.parse(**args)


def test_local_timestamp_is_wall_clock():
    t = parse_mod.local_ts("2026-01-15T07:48:32.000Z", TZ)
    assert t == datetime(2026, 1, 15, 7, 48, 32, tzinfo=TZ)
    assert t.astimezone(timezone.utc).hour == 13  # CST = UTC-6


def test_utc_timestamp_handles_nanoseconds():
    assert parse_mod.utc_ts("2026-01-15T14:03:09.557997188Z/") == datetime(2026, 1, 15, 14, 3, 9, 557997, tzinfo=timezone.utc)


def test_last_bolus_is_newest_not_last_in_list():
    d = _parse()
    assert d.last_bolus.delivered == 1.25
    assert d.last_bolus.time == datetime(2026, 1, 15, 7, 9, 11, tzinfo=TZ)
    assert d.last_bolus.iob == 0.6
    assert d.last_bolus.bg_input == 123  # x100-encoded value normalized


def test_today_totals():
    d = _parse()
    assert d.bolus_insulin_today == 1.75
    assert d.carbs_today == 15.0
    assert d.last_carbs == 15.0


def test_pump_mode_and_since_spans_midnight():
    d = _parse()
    assert d.pump_mode == "automated"
    assert d.pump_mode_since == datetime(2026, 1, 14, 13, 8, 29, tzinfo=TZ)


def test_pod_and_sensor():
    d = _parse()
    assert d.pod_changed == datetime(2026, 1, 14, 12, 49, 38, tzinfo=TZ)
    assert d.pod_expires == datetime(2026, 1, 17, 12, 49, 38, tzinfo=TZ)
    assert d.pod_age_hours(NOW) == 19.8
    assert d.cgm_sensor_changed == datetime(2026, 1, 14, 12, 32, 27, tzinfo=TZ)


def test_sync_freshness_from_insulet_transfer():
    d = _parse()
    assert d.last_sync == datetime(2026, 1, 15, 14, 33, 9, 557000, tzinfo=timezone.utc)
    assert d.last_sync_type == "ON_DEMAND"
    assert d.data_through == datetime(2026, 1, 15, 7, 48, 32, tzinfo=TZ)
    assert d.data_age_minutes(NOW) == 51.5


def test_stats_whitelist():
    d = _parse()
    assert d.stats["inRangePercentage"] == 71
    assert "bmi" not in d.stats


def test_empty_payloads_do_not_crash():
    d = _parse(graph=None, devices=None, connections=None, stats=None)
    assert d.pump_mode == "unknown"
    assert d.last_bolus is None
    assert d.data_through is None
    assert d.bolus_insulin_today == 0
