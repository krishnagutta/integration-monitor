# Integration Monitoring Agent

A standalone Python agent that monitors Lyft's PTECH Jira project for Workday integration error tickets, classifies them using Claude AI, and takes automated action (add comment, transition ticket, escalate). After each run it posts a summary digest to the `#ptech-integration-jira` Slack channel. Designed to run every 30 minutes via GitHub Actions with zero infrastructure overhead.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all required values
```

### 3. Get a Jira Personal Access Token (PAT)

1. Go to **https://jira.lyft.net**
2. Click your avatar → **Profile**
3. Navigate to **Personal Access Tokens**
4. Click **Create token**, give it a name, set expiry
5. Copy the token and set it as `JIRA_API_TOKEN` in your `.env`

Set `JIRA_USERNAME` to your Lyft Jira username (e.g. `workday-bot`).

---

## Run commands

```bash
# Dry run — classify and log, no changes to Jira or Slack
python agent.py --dry-run

# Dry run with extended lookback (useful for testing with historical tickets)
python agent.py --dry-run --lookback 168

# Live run (last 1 hour of tickets)
python agent.py --lookback 1

# Live run using env-var defaults
python agent.py
```

---

## Cron setup (local/server)

Add to crontab to run every 30 minutes:

```cron
*/30 * * * * cd /path/to/integration-monitor && python agent.py --lookback 1 >> /var/log/integration-monitor.log 2>&1
```

---

## Error types → actions

| Error Type        | Meaning                                                    | Action               |
|-------------------|------------------------------------------------------------|----------------------|
| `TRANSIENT`       | Connection timeout, network blip, temp unavailability      | `AUTO_RETRY`         |
| `DATA_VALIDATION` | Missing field, invalid format, bad employee data           | `CREATE_DATA_FIX_TASK` |
| `AUTH_FAILURE`    | SFTP credentials failed, API token expired, cert issue     | `ESCALATE_IMMEDIATELY` |
| `VOLUME_ANOMALY`  | Expected records but got 0 or far fewer                    | `HOLD_FOR_REVIEW`    |
| `PARTIAL_FAILURE` | Most records processed but some failed                     | `INVESTIGATE`        |
| `UNKNOWN`         | Cannot determine from available info                       | `INVESTIGATE`        |

---

## Validate credentials

```bash
# 1. Test Jira auth
curl -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  "https://jira.lyft.net/rest/api/2/myself"
# 200 = success, 401 = bad credentials

# 2. Test JQL query
curl -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  "https://jira.lyft.net/rest/api/2/search?jql=project=PTECH+AND+issuetype=Bug+AND+labels=integration_event+AND+status=Open&maxResults=5"
```

---

## Known Limitations / Phase 2 TODOs

1. **Workday rerun is manual** — The agent comments on tickets and transitions them to *In Progress*, but the actual Workday integration rerun must be triggered manually in Workday. Phase 2 will add `workday_client.py` to trigger reruns programmatically via the Workday REST API.

2. **No audit log** — Phase 2 will add SQLite tracking of every agent action to measure MTTR improvement over time.

3. **Cron only** — Agent runs on a schedule. Phase 2 can add a Slack event webhook to trigger immediately when a new ticket notification arrives.
