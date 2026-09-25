# Contributing to Glooko for Home Assistant

Thanks for helping. This is a small, volunteer-run, open-source project. Bug reports,
Glooko payload samples (sanitized), docs fixes and code are all welcome.

> [!IMPORTANT]
> This integration touches **health data**. Two rules override everything else in this document:
> 1. **Never post real medical data, credentials, session cookies or your Glooko patient code**
>    in issues, pull requests, discussions, commits or test fixtures. Redact or synthesize.
> 2. **The integration stays read-only.** We will not merge anything that writes to a Glooko,
>    Insulet or pump account (no creating/editing/deleting records, no acknowledging alarms,
>    no settings changes). The sign-in POST is the only non-GET request allowed.

---

## How the repository is set up

- `main` is protected. Only the maintainer (**@tivotyro**) can update it.
- Everyone else contributes through **fork → branch → pull request**. You cannot push to this
  repository directly, and that is intentional.
- Every PR must pass CI (`hassfest` and `tests`) before a maintainer can merge it.
- PRs are **squash-merged**, so your branch history doesn't need to be tidy. The PR title becomes
  the commit message, so make the title clear.
- For first-time contributors, a maintainer has to approve the CI run before it starts. This is a
  standard GitHub safety setting, not a judgment about your PR.

## Ways to contribute

| You want to… | Do this |
|---|---|
| Ask a question / get setup help | Open a [Discussion](../../discussions) |
| Report a bug | Open an issue with the **Bug report** template. Attach redacted diagnostics |
| Suggest a feature or new sensor | Open an issue with the **Feature request** template |
| Report a security problem | **Do not open an issue.** See [SECURITY.md](SECURITY.md) |
| Fix something / add something | Read on |

If you plan a larger change (a new platform, new endpoints, refactors), open an issue first so we can
agree on the approach before you spend time on it.

## Development setup

Requirements: Python 3.13+, git, a GitHub account.

```bash
# 1. Fork on GitHub (button top-right), then:
git clone https://github.com/<you>/glookup-ha-integration.git
cd glookup-ha-integration
git remote add upstream https://github.com/mmxca/glookup-ha-integration.git

# 2. Environment
python3 -m venv .venv
. .venv/bin/activate
pip install pytest-homeassistant-custom-component

# 3. Run the tests
python -m pytest
```

`tests/test_parse.py` needs only `pytest` (no Home Assistant), which is handy for quick parser work.

### Trying it in a real Home Assistant

Easiest: a throwaway HA instance (a Docker container or a dev VM, not your production HA).

```bash
docker run -d --name ha-dev -p 8123:8123 \
  -v "$PWD/.ha-config:/config" \
  -v "$PWD/custom_components:/config/custom_components" \
  ghcr.io/home-assistant/home-assistant:stable
```

Then open <http://localhost:8123>, finish onboarding, and add the **Glooko** integration.
Enable debug logs with:

```yaml
logger:
  logs:
    custom_components.glooko: debug
```

## Making a change

1. Sync with upstream and branch:
   ```bash
   git fetch upstream
   git switch -c fix/short-description upstream/main
   ```
2. Make the change. Keep PRs focused. One fix or feature per PR is much easier to review.
3. Add or update tests:
   - Parser changes → `tests/test_parse.py` with **synthetic** data in `tests/fixtures/`.
   - Config flow / setup / entity changes → `tests/test_init.py`.
4. If you added or renamed an entity or config field, update `strings.json` **and**
   `translations/en.json` (keep them identical), and the entity table in `README.md`.
5. Run `python -m pytest` locally. It must pass.
6. Push to your fork and open a PR against `mmxca/glookup-ha-integration:main`. Fill in the template.

### Code guidelines

- Follow Home Assistant's [integration conventions](https://developers.home-assistant.io/docs/creating_component_index):
  config-flow only (no YAML config), `DataUpdateCoordinator`, `has_entity_name`, translation keys,
  `entry.runtime_data`.
- Everything that talks to the network is async (`aiohttp` via HA's client session). No blocking I/O
  in the event loop.
- `parse.py` must stay free of Home Assistant imports, so it stays testable in isolation.
- Glooko timestamps: event times are **local wall-clock with a fake `Z`** (use `local_ts`);
  sync/transfer times are **real UTC** (use `utc_ts`). Mixing these up is the most common bug.
- Be gentle with Glooko's servers. No new per-poll requests without discussing it first. The default
  poll is 10 minutes and the minimum is 5.
- No new third-party Python requirements unless there's a strong reason (`manifest.json` → `requirements`).
- Type hints on new code. Keep functions small and named plainly.

### Test fixtures and sample payloads

Real Glooko responses are the best way to support new pumps and fields, but they are full of health
data. If you want to share one:

- Replace every value that identifies you: email, name, DOB, `glookoCode`, `guid`s, serial numbers,
  `integrationUserId`, file names.
- Shift or replace dates, and replace glucose, insulin and carb values with plausible fake numbers.
- Keep the **structure** (keys, nesting, types, timestamp formats) exactly as received. That's the useful part.

The `.gitignore` blocks `*.jsonl` and `snap_*.json` to make accidentally committing a raw export harder.

## Commit messages and PR titles

Short, imperative, specific: `Fix pod expiry when site change and reservoir change differ`,
`Add sensor for last temporary basal`. Reference issues with `Fixes #12` in the PR description.

## Reviews

A maintainer will review as time allows. This is a spare-time project, so please be patient.
We may ask for changes, push small fixups to your branch (leave "Allow edits by maintainers" checked),
or close PRs that don't fit the project's scope (for example, anything that writes to an account).

## Licensing

By submitting a contribution you agree it is licensed under this project's [MIT License](LICENSE).

## Conduct

Be decent. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Many people here live with diabetes. Be
kind about questions, and never shame anyone's numbers.
