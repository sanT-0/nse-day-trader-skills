# Platform-neutral use

The repository has three separate layers:

1. **Standard-library Python CLIs** — work without an AI application.
2. **Portable `SKILL.md` folders** — usable by agents that support the Agent
   Skills folder convention or custom instruction bundles.
3. **Optional platform metadata** — OpenCode and Claude plugin files are
   adapters, not runtime requirements.

## Standalone CLI

```bash
python scripts/run.py --list
python scripts/run.py market --universe nifty100
python scripts/run.py flows --days 5 --top 10
```

Every command supports `--help`. State is ordinary JSON/Markdown under
`./nse-trader/` or `NSE_TRADER_STATE_DIR`.

## Generic agent installation

Many agents discover `SKILL.md` folders from `~/.agents/skills`:

```bash
python scripts/install.py --target agents
```

For any other application, use its custom skills/instructions directory:

```bash
python scripts/install.py --destination /path/from/your/app/docs
```

If an application cannot execute local Python, package and upload the relevant
skill as reference material:

```bash
python scripts/package_skills.py --skill nse-trader-scanner
```

The agent must still have permission to run Python and reach the data sources
for live analysis. A web chat that only reads uploaded files cannot monitor the
market or run background alerts.

## Direct repository source

Agents capable of recursively finding `SKILL.md` can use the clone itself as a
skill source. This is the easiest update path: `git pull` refreshes everything.

## What “portable” does not mean

- It does not bypass an application's tool, network or filesystem permissions.
- It does not guarantee background execution or push notifications.
- It does not convert the scripts into broker APIs.
- Platform-specific installers may use different paths; follow that platform's
  current documentation or use `--destination`.
