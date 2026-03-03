import logging
from datetime import datetime, timezone

import requests

import config

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api/chat.postMessage"

PRIORITY_EMOJI = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}
ACTION_EMOJI = {
    "AUTO_RETRY": "🔄",
    "ESCALATE_IMMEDIATELY": "🚨",
    "CREATE_DATA_FIX_TASK": "📋",
    "HOLD_FOR_REVIEW": "👀",
    "INVESTIGATE": "🔍",
}


def _post_message(blocks: list, text: str, dry_run: bool) -> bool:
    """Internal helper to post a Block Kit message to Slack."""
    if not config.SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not set — skipping Slack notification")
        return False

    if dry_run:
        logger.info("[DRY RUN] Would post to Slack channel %s:\n%s", config.SLACK_CHANNEL_ID, text)
        return True

    headers = {
        "Authorization": f"Bearer {config.SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "channel": config.SLACK_CHANNEL_ID,
        "text": text,
        "blocks": blocks,
    }
    try:
        response = requests.post(SLACK_API_URL, json=payload, headers=headers, timeout=10)
        data = response.json()
        if not data.get("ok"):
            logger.error("Slack API error: %s", data.get("error"))
            return False
        return True
    except Exception as e:
        logger.error("Failed to post Slack message: %s", e)
        return False


def notify_ticket_action(
    issue_key: str,
    ticket_url: str,
    classification: dict,
    action_taken: str,
    dry_run: bool,
) -> bool:
    """Post a per-ticket Block Kit message. Only called for HIGH priority or ESCALATE_IMMEDIATELY."""
    priority = classification.get("priority", "MEDIUM")
    error_type = classification.get("error_type", "UNKNOWN")
    integration_name = classification.get("integration_name") or "Unknown"
    root_cause = classification.get("root_cause_summary", "No summary available.")

    p_emoji = PRIORITY_EMOJI.get(priority, "⚠️")
    a_emoji = ACTION_EMOJI.get(action_taken, "🔍")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{p_emoji} Integration Error — {issue_key}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{ticket_url}|View {issue_key} in Jira>*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Error Type:*\n{error_type}"},
                {"type": "mrkdwn", "text": f"*Integration:*\n{integration_name}"},
                {"type": "mrkdwn", "text": f"*Priority:*\n{p_emoji} {priority}"},
                {"type": "mrkdwn", "text": f"*Action Taken:*\n{a_emoji} {action_taken}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
        },
        {"type": "divider"},
    ]

    fallback_text = f"{p_emoji} {issue_key} — {error_type} | {action_taken} | {root_cause[:100]}"
    return _post_message(blocks, fallback_text, dry_run)


def post_digest(results: list[dict], dry_run: bool) -> bool:
    """Post a summary digest after all tickets are processed."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total = len(results)
    auto_retried = sum(1 for r in results if r.get("action") == "AUTO_RETRY")
    escalated = sum(1 for r in results if r.get("action") == "ESCALATE_IMMEDIATELY")
    data_fix = sum(1 for r in results if r.get("action") == "CREATE_DATA_FIX_TASK")
    held = sum(1 for r in results if r.get("action") in ("HOLD_FOR_REVIEW", "INVESTIGATE"))

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🤖 Integration Monitor — {now}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Total Tickets:*\n{total}"},
                {"type": "mrkdwn", "text": f"*🔄 Auto-Retried:*\n{auto_retried}"},
                {"type": "mrkdwn", "text": f"*🚨 Escalated:*\n{escalated}"},
                {"type": "mrkdwn", "text": f"*📋 Data Fix Needed:*\n{data_fix}"},
                {"type": "mrkdwn", "text": f"*👀 Held for Review:*\n{held}"},
            ],
        },
    ]

    escalated_tickets = [r for r in results if r.get("action") == "ESCALATE_IMMEDIATELY"]
    if escalated_tickets:
        ticket_lines = "\n".join(
            f"• <{r['url']}|{r['key']}> — {r.get('integration') or 'Unknown'}"
            for r in escalated_tickets
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🚨 Escalated Tickets:*\n{ticket_lines}",
                },
            }
        )

    blocks.append({"type": "divider"})

    fallback_text = (
        f"🤖 Integration Monitor {now} | "
        f"Total: {total} | Auto-Retried: {auto_retried} | Escalated: {escalated} | "
        f"Data Fix: {data_fix} | Held: {held}"
    )
    return _post_message(blocks, fallback_text, dry_run)
