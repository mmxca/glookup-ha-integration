# Glooko for Home Assistant

[![Validate](https://github.com/mmxca/glookup-ha-integration/actions/workflows/validate.yml/badge.svg)](https://github.com/mmxca/glookup-ha-integration/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A **read-only** Home Assistant custom integration that brings your insulin-pump data from
[Glooko](https://my.glooko.com) into Home Assistant: last bolus, IOB at that bolus, carbs,
pump mode (Automated / Limited / Manual / HypoProtect), pod change and expiry, CGM sensor change,
pump alarms, and how fresh the data is.

It was built and tested against an **Insulet Omnipod 5** (iPhone app) that shares its data with Glooko.
Other pumps that sync to Glooko should mostly work, but Omnipod 5 is the only one verified.

> [!WARNING]
> **Not a medical device. Do not make treatment decisions from this data.**
> The data is delayed (see [How fresh is the data?](#how-fresh-is-the-data)), may be incomplete,
> and relies on an undocumented Glooko API that can change or break without notice.
> Always use your pump controller for dosing decisions.

---

## What you get

All entities belong to one **Glooko** service device.

| Entity | Type | Notes |
|---|---|---|
| `sensor.glooko_last_bolus` | U | Delivered units. Attributes: time, programmed, recommended, meal/correction portion, carbs, IOB at bolus, BG input, overrides, boluses today |
| `sensor.glooko_last_bolus_time` | timestamp | |
| `sensor.glooko_iob_at_last_bolus` | U | IOB the pump reported **at the moment of the last bolus**, not live IOB |
| `sensor.glooko_bolus_insulin_today` | U | Sum of today's boluses (local midnight reset) |
| `sensor.glooko_last_carbs` / `sensor.glooko_carbs_today` | g | From carbs entered in the bolus calculator |
| `sensor.glooko_pump_mode` | enum | `automated`, `limited`, `manual`, `hypoprotect`, `unknown`. Attribute `since` |
| `binary_sensor.glooko_automated_mode` | on/off | On when the pump is in Automated mode |
| `sensor.glooko_pod_changed` / `sensor.glooko_pod_expires` | timestamp | Expiry = change + 72 h |
| `sensor.glooko_pod_age` | h | |
| `sensor.glooko_cgm_sensor_changed` | timestamp | |
| `sensor.glooko_last_pump_alarm` | timestamp | |
| `sensor.glooko_last_glooko_sync` | timestamp (diagnostic) | When Glooko last pulled from the pump cloud. Attributes: transfer type, connection state |
| `sensor.glooko_pump_data_through` | timestamp (diagnostic) | Newest pump data Glooko has |
| `sensor.glooko_pump_data_age` | min (diagnostic) | Now minus "data through" |
| `binary_sensor.glooko_data_stale` | problem (diagnostic) | On when data age exceeds the threshold (default 120 min) |
| `sensor.glooko_time_in_range_14d` | % | Plus low/high % and CGM active % as attributes |
| `sensor.glooko_gmi_14d` | % | |
| `sensor.glooko_average_glucose_14d` | mg/dL | CV as attribute |

Not available from Glooko: **live IOB, reservoir level, pod battery, current basal rate as a number.**
Glooko only stores what the pump cloud hands it.

---

## Requirements

- Home Assistant **2025.1** or newer.
- A Glooko account with your pump connected. For Omnipod 5: in the Omnipod 5 app, turn on data sharing
  with Glooko (Insulet's "Insulet-provided Glooko"). Confirm your pump data shows up at
  <https://my.glooko.com> before installing this.
- Your Glooko **email and password**. Accounts with **two-factor authentication are not supported** yet.
- Outbound HTTPS from Home Assistant to `*.api.glooko.com`.

---

## Installation

### Option A: HACS (custom repository)

1. In Home Assistant open **HACS → ⋮ (top right) → Custom repositories**.
2. Repository: `https://github.com/mmxca/glookup-ha-integration`, Type: **Integration** → **Add**.
3. Search HACS for **Glooko** → **Download**.
4. **Restart Home Assistant** (Settings → System → ⋮ → Restart).

### Option B: Manual

1. Copy the folder `custom_components/glooko` from this repo into your Home Assistant config directory,
   so you end up with:
   ```
   <config>/custom_components/glooko/__init__.py
   <config>/custom_components/glooko/manifest.json
   ...
   ```
   (`<config>` is the folder that contains `configuration.yaml`. With the Samba, SSH or
   File editor add-ons it's `/config`.)
2. **Restart Home Assistant.**

Example with the SSH add-on:

```bash
cd /config
git clone https://github.com/mmxca/glookup-ha-integration /tmp/glooko
mkdir -p custom_components && cp -r /tmp/glooko/custom_components/glooko custom_components/
rm -rf /tmp/glooko
ha core restart
```

---

## Configuration (credentials are entered in Home Assistant)

No YAML. Home Assistant collects the credentials through its UI:

1. **Settings → Devices & services → + Add integration → Glooko.**
2. Enter your Glooko **email**, **password** and **region** (US accounts: *United States*).
3. The integration performs a real sign-in to validate them before saving. Errors you may see:
   - *Invalid email or password*
   - *This Glooko account requires two-factor authentication* (not supported)
   - *Could not reach Glooko*: network or wrong region
4. Done. Entities appear under the **Glooko** device.

**Where the credentials live:** Home Assistant stores them in its config-entry store
(`<config>/.storage/core.config_entries`), like every other UI-configured integration. That file is
not encrypted at rest. Protect your HA backups and disk accordingly. Nothing is written anywhere else,
and diagnostics downloads redact email, password, Glooko patient code, device IDs and serials.

**If the password changes** (or Glooko starts rejecting it), Home Assistant shows a
**Re-authenticate** notification under Settings → Devices & services. Enter the new password there.

### Options

Settings → Devices & services → Glooko → **Configure**:

| Option | Default | Range |
|---|---|---|
| Polling interval | 10 min | 5-60 min |
| Mark data stale after | 120 min | 30-1440 min |
| Ask Glooko to sync every | 30 min | 0 (off) or 15-240 min |

Please keep polling gentle. Each poll is 3 small GET requests (a 4th, statistics, once an hour).

**Sync trigger:** Glooko only pulls new pump data from the pump cloud when someone signs in on the
Glooko **website**. The API sign-in used for polling does not count. With *Ask Glooko to sync every*
enabled, the integration performs a website sign-in at most that often, and only when Glooko reports
it is ready for a sync (`syncState: SYNC_ALLOWED`). It re-polls about 90 seconds later to pick up the
fresh data. That is one extra sign-in per interval, and nothing in your account is changed. The
outcome is shown on `sensor.glooko_last_glooko_sync` (`sync_state`, `last_sync_trigger`,
`sync_trigger_result`). Set it to 0 to turn it off. The check runs on each poll, so the effective
interval rounds up to a multiple of the polling interval (for example, 15 min with 5-min polling, 20 min with 10-min polling).

---

## How fresh is the data?

Measured on a real Omnipod 5 account (September 2026):

- The Omnipod 5 app uploads to Insulet's cloud about **every 5 minutes**.
- Glooko pulls from Insulet **on demand** (transfer type `ON_DEMAND`), requesting data only up to
  **now minus 30 minutes**. When a pull happens, the newest pump data is typically **33-45 minutes old**.
- Glooko only pulls when someone signs in on the Glooko website. The API sign-in used for polling does
  **not** trigger it. Without that, pulls may **not happen for many hours** (17 h observed overnight).
- A website sign-in triggers a pull within about 1 second. Glooko then enforces a short cooldown
  (`syncState: ALREADY_SYNCED`, about 12 minutes observed).
- With the sync trigger on (default: every 30 min), pump data typically stays **about 35-65 minutes behind**.

So: expect roughly **35-65 minutes of delay** with the sync trigger on, and potentially hours with it off. This is fine for logging, dashboards and
"did I bolus for lunch?" reminders. It is not for anything time-critical.

---

## Examples

### Dashboard card

```yaml
type: entities
title: Omnipod 5 (via Glooko)
entities:
  - entity: sensor.glooko_pump_mode
  - entity: sensor.glooko_last_bolus
  - entity: sensor.glooko_last_bolus_time
  - entity: sensor.glooko_iob_at_last_bolus
  - entity: sensor.glooko_bolus_insulin_today
  - entity: sensor.glooko_carbs_today
  - entity: sensor.glooko_pod_expires
  - entity: sensor.glooko_pump_data_age
```

### Automation: pod expires in 8 hours

```yaml
alias: Pod change reminder
triggers:
  - trigger: time_pattern
    minutes: "/15"
conditions:
  - condition: template
    value_template: >
      {% set exp = states('sensor.glooko_pod_expires') | as_datetime %}
      {{ exp is not none and 0 < (exp - now()).total_seconds() < 8*3600 }}
actions:
  - action: notify.notify
    data:
      message: "Pod expires {{ states('sensor.glooko_pod_expires') | as_datetime | relative_time }} from now."
mode: single
```

### Automation: Glooko data went stale

```yaml
alias: Glooko data stale
triggers:
  - trigger: state
    entity_id: binary_sensor.glooko_data_stale
    to: "on"
    for: "00:15:00"
actions:
  - action: notify.notify
    data:
      message: "Glooko pump data is {{ states('sensor.glooko_pump_data_age') }} min old."
```

---

## How it works

- Signs in with `POST /api/v2/users/sign_in`, falls back to the v3
  sign-in if the account requires it, and keeps the session cookie in memory. It re-signs in automatically
  when the session expires.
- Each poll (read-only `GET`s against `https://<region>.api.glooko.com`):
  - `/api/v3/graph/data`: yesterday + today, pump series (boluses, carbs, mode spans, pod/sensor changes, alarms)
  - `/api/v3/devices_and_settings`: pump model, last sync
  - `/api/v3/cloud_connections`: Insulet cloud transfers (freshness)
  - `/api/v3/graph/statistics/overall`: 14-day stats (hourly)
- Sync trigger (optional, default every 30 min): `GET` + `POST https://<region>.my.glooko.com/users/sign_in`,
  the same form a person uses. Sign-ins are the only non-GET requests the integration ever makes.
- Glooko quirk handled: event timestamps are the pump's **local wall-clock time with a `Z` suffix**.
  They're interpreted in Home Assistant's configured time zone, so **set HA's time zone to the pump's**.

This is an unofficial integration, not affiliated with Glooko or Insulet. It uses the same web API as
the Glooko website and the [nightscout-connect](https://github.com/nightscout/nightscout-connect) Glooko
source.

---

## Troubleshooting

- **Entities are `unknown` right after setup:** Glooko may not have pulled from your pump cloud yet.
  Open <https://my.glooko.com> once, then wait for the next poll.
- **Times are off by hours:** HA's time zone (Settings → System → General) must match the pump's.
- **Debug logging:**
  ```yaml
  logger:
    logs:
      custom_components.glooko: debug
  ```
- **Diagnostics:** Settings → Devices & services → Glooko → ⋮ → *Download diagnostics* (secrets redacted).

---

## Contributing

Contributions are welcome through **fork → branch → pull request**. `main` is protected, and only the
maintainers merge. See **[CONTRIB.md](CONTRIB.md)** for setup, tests and guidelines,
[SECURITY.md](SECURITY.md) for reporting vulnerabilities privately, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Questions and setup help: [Discussions](https://github.com/mmxca/glookup-ha-integration/discussions).

Quick start for developers:

```bash
python -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component
python -m pytest            # parser + config-flow + setup tests
```

Roadmap: v2 incremental endpoints (full history, alarms with codes), basal-rate detail,
`glooko.refresh` service.

## License

MIT
