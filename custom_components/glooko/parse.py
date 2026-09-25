"""Pure parsing of Glooko API payloads (no Home Assistant imports; unit-testable).

Glooko quirk: pump/CGM event timestamps are the device's *local wall-clock time*
serialized with a misleading 'Z' suffix (e.g. 07:48 Central -> "07:48:32.000Z").
Sync/transfer timestamps (syncTimestamp, updatedAt, transfer 'timestamp') are true UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from .const import INSULET_INTEGRATION, MODE_SERIES, POD_LIFETIME_HOURS


def local_ts(value: str | None, tz: tzinfo) -> datetime | None:
    """Parse a Glooko local-clock timestamp ('...Z' that is really local) into aware local time."""
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value.replace("Z", "")[:26])
    except ValueError:
        return None
    return naive.replace(tzinfo=tz)


def utc_ts(value: str | None) -> datetime | None:
    """Parse a true-UTC timestamp."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Glooko sometimes sends 9-digit fractions ('.557997188Z').
        try:
            head, _, frac = value.rstrip("Z/").partition(".")
            dt = datetime.fromisoformat(f"{head}.{frac[:6] or '0'}+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def glooko_day_range(start: date, end: date) -> tuple[str, str]:
    """Glooko graph windows are expressed in local wall-clock time with a 'Z'."""
    return f"{start.isoformat()}T00:00:00.000Z", f"{end.isoformat()}T23:59:59.999Z"


@dataclass
class Bolus:
    time: datetime
    delivered: float | None
    programmed: float | None
    carbs: float | None
    iob: float | None
    bg_input: float | None
    bg_source: str | None
    meal_portion: float | None
    correction_portion: float | None
    recommended: float | None
    manual: bool | None
    override_above: bool | None
    override_below: bool | None
    interrupted: bool | None


@dataclass
class GlookoData:
    """Everything the entities need, already normalized."""

    fetched_at: datetime
    pump_name: str | None = None
    last_bolus: Bolus | None = None
    boluses_today: list[Bolus] = field(default_factory=list)
    bolus_insulin_today: float | None = None
    carbs_today: float | None = None
    last_carbs: float | None = None
    last_carbs_time: datetime | None = None
    pump_mode: str = "unknown"
    pump_mode_since: datetime | None = None
    pod_changed: datetime | None = None
    cgm_sensor_changed: datetime | None = None
    last_pump_alarm: datetime | None = None
    last_sync: datetime | None = None
    last_sync_type: str | None = None
    data_through: datetime | None = None
    connection_state: str | None = None
    sync_state: str | None = None
    last_sync_trigger: datetime | None = None
    sync_trigger_result: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def pod_expires(self) -> datetime | None:
        return self.pod_changed + timedelta(hours=POD_LIFETIME_HOURS) if self.pod_changed else None

    def pod_age_hours(self, now: datetime) -> float | None:
        if not self.pod_changed:
            return None
        return round((now - self.pod_changed).total_seconds() / 3600, 1)

    def data_age_minutes(self, now: datetime) -> float | None:
        if not self.data_through:
            return None
        return round((now - self.data_through).total_seconds() / 60, 1)


def _f(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _bg(value: Any) -> float | None:
    v = _f(value)
    # v2 endpoints encode mg/dL x100; v3 graph sends plain mg/dL.
    if v is not None and v > 1000:
        v = round(v / 100)
    return v


def _bolus(point: dict[str, Any], tz: tzinfo) -> Bolus | None:
    t = local_ts(point.get("timestamp"), tz)
    if t is None:
        return None
    return Bolus(
        time=t,
        delivered=_f(point.get("insulinDelivered")),
        programmed=_f(point.get("insulinProgrammed")),
        carbs=_f(point.get("carbsInput")),
        iob=_f(point.get("insulinOnBoard")),
        bg_input=_bg(point.get("bloodGlucoseInput")),
        bg_source=point.get("bloodGlucoseInputSource"),
        meal_portion=_f(point.get("insulinRecommendationForCarbs")),
        correction_portion=_f(point.get("insulinRecommendationForCorrection")),
        recommended=_f(point.get("totalInsulinRecommendation")),
        manual=point.get("isManual"),
        override_above=point.get("isOverrideAbove"),
        override_below=point.get("isOverrideBelow"),
        interrupted=point.get("isInterrupted"),
    )


def _latest(points: list[dict[str, Any]] | None, tz: tzinfo, key: str = "timestamp") -> datetime | None:
    times = [t for p in points or [] if (t := local_ts(p.get(key), tz))]
    return max(times) if times else None


def parse(
    *,
    graph: dict[str, Any] | None,
    devices: dict[str, Any] | None,
    connections: list[dict[str, Any]] | None,
    stats: dict[str, Any] | None,
    tz: tzinfo,
    now: datetime,
) -> GlookoData:
    """Normalize raw Glooko payloads."""
    data = GlookoData(fetched_at=now)
    series: dict[str, Any] = (graph or {}).get("series") or {}
    today = now.astimezone(tz).date()

    # --- boluses (deliveredBolus has the full detail) ---
    boluses = sorted(
        (b for p in series.get("deliveredBolus") or [] if (b := _bolus(p, tz))),
        key=lambda b: b.time,
    )
    if boluses:
        data.last_bolus = boluses[-1]
    data.boluses_today = [b for b in boluses if b.time.date() == today]
    data.bolus_insulin_today = round(sum(b.delivered or 0 for b in data.boluses_today), 2)

    # --- carbs ---
    carbs = sorted(
        ((t, _f(p.get("carbs"))) for p in series.get("carbAll") or [] if (t := local_ts(p.get("timestamp"), tz))),
        key=lambda x: x[0],
    )
    carbs = [(t, c) for t, c in carbs if c]
    if carbs:
        data.last_carbs_time, data.last_carbs = carbs[-1]
    data.carbs_today = round(sum(c for t, c in carbs if t.date() == today), 1)

    # --- pump mode: the span with the latest end wins ---
    best: tuple[datetime, datetime | None, str] | None = None
    for key, mode in MODE_SERIES.items():
        for span in series.get(key) or []:
            end = local_ts(span.get("endTimestamp"), tz) or local_ts(span.get("timestamp"), tz)
            start = local_ts(span.get("timestamp"), tz)
            if end and (best is None or end > best[0]):
                best = (end, start, mode)
    if best:
        data.pump_mode, data.pump_mode_since = best[2], best[1]
        # Glooko splits one continuous mode into segments (at midnight and at every sync).
        # Walk back through touching segments until the start stops moving.
        spans = [
            (local_ts(s.get("timestamp"), tz), local_ts(s.get("endTimestamp"), tz))
            for key, mode in MODE_SERIES.items()
            if mode == data.pump_mode
            for s in series.get(key) or []
        ]
        spans = [(a, b) for a, b in spans if a and b]
        changed = True
        while changed and data.pump_mode_since:
            changed = False
            for start, end in spans:
                if start < data.pump_mode_since and abs((end - data.pump_mode_since).total_seconds()) <= 2:
                    data.pump_mode_since = start
                    changed = True

    # --- pod / sensor / alarms ---
    data.pod_changed = max(
        [t for t in (_latest(series.get("setSiteChange"), tz), _latest(series.get("reservoirChange"), tz)) if t],
        default=None,
    )
    data.cgm_sensor_changed = _latest(series.get("cgmSensorChange"), tz)
    data.last_pump_alarm = _latest(series.get("pumpAlarm"), tz)

    # --- device + sync freshness ---
    for dev in (devices or {}).get("devices") or []:
        if dev.get("type") == "pump" or dev.get("deviceClassification") == "pump":
            data.pump_name = dev.get("displayName")
            data.last_sync = utc_ts(dev.get("lastSyncTimestampUtc") or dev.get("lastSyncTimestamp"))
            break

    for conn in connections or []:
        if conn.get("integration") != INSULET_INTEGRATION:
            continue
        data.connection_state = conn.get("state")
        data.sync_state = conn.get("syncState")
        transfers = [t for t in conn.get("transfers") or [] if t.get("success") or t.get("state") == "SUCCESSFUL"]
        transfers.sort(key=lambda t: t.get("timestamp") or "")
        if transfers:
            latest = transfers[-1]
            data.last_sync = utc_ts(latest.get("timestamp")) or data.last_sync
            data.last_sync_type = latest.get("type")
            end = ((latest.get("metadata") or {}).get("dataRange") or {}).get("end")
            data.data_through = local_ts(end, tz)
        break

    if data.data_through is None:
        # Fall back to the newest pump-originated point in the graph.
        candidates = [data.last_bolus.time if data.last_bolus else None, best[0] if best else None, data.pod_changed]
        candidates = [c for c in candidates if c]
        data.data_through = max(candidates) if candidates else None

    # --- 14-day statistics (only a few well-defined fields) ---
    if stats:
        for key in ("inRangePercentage", "lowPercentage", "highPercentage", "gmi", "averageBg",
                    "coefficientOfVariation", "activeCgmTimePercentage", "carbsPerDay"):
            if key in stats:
                data.stats[key] = stats[key]

    return data
