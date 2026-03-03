# integration-monitor

Lyft People Tech — Workday Integration Monitoring Agent

Monitors the PTECH Jira project for `integration_event` bug tickets, classifies them with Claude AI, takes automated action, and posts Slack digests. Runs every 30 minutes via GitHub Actions.

## Quick start

See [`integration-monitor/README.md`](integration-monitor/README.md) for full setup and run instructions.

## Repo structure

```
integration-monitor/           # repo root
├── .github/
│   └── workflows/
│       └── integration-monitor.yml   # GitHub Actions cron workflow
├── integration-monitor/              # Python agent code
│   ├── agent.py                      # Main orchestrator
│   ├── jira_client.py                # Jira REST API wrapper
│   ├── classifier.py                 # Claude AI error classifier
│   ├── slack_notifier.py             # Slack digest + alerts
│   ├── config.py                     # Env var loader
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── .gitignore
└── README.md
```

## GitHub Actions secrets

Configure these in **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `JIRA_USERNAME` | Your Lyft Jira username |
| `JIRA_API_TOKEN` | Your Jira PAT |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | `C09KBAUMZMJ` |
