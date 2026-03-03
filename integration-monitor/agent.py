"""
Integration Monitoring Agent — Main Orchestrator

Monitors Lyft's PTECH Jira project for Workday integration error tickets,
classifies them using Claude AI, takes automated action, and posts a Slack digest.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

import config
from classifier import classify_error
from jira_client import JiraClient
from slack_notifier import notify_ticket_action, post_digest


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


# ---------------------------------------------------------------------------
# Comment templates
# ---------------------------------------------------------------------------

def _comment_auto_retry(c: dict) -> str:
    return (
        "🤖 Integration Monitor — Auto-Retry Triggered\n\n"
        f"Error Type: {c.get('error_type', 'UNKNOWN')}\n"
        f"Integration: {c.get('integration_name') or 'Unknown'}\n"
        f"Root Cause: {c.get('root_cause_summary', 'N/A')}\n\n"
        "Action: Automatically retrying this integration run. Ticket moved to In Progress.\n"
        "Note: Workday rerun must be triggered manually until Workday API is connected (Phase 2)."
    )


def _comment_data_fix(c: dict) -> str:
    return (
        "🤖 Integration Monitor — Data Fix Required\n\n"
        f"Error Type: DATA_VALIDATION\n"
        f"Integration: {c.get('integration_name') or 'Unknown'}\n"
        f"Affected Records: {c.get('affected_records') or 'Unknown'}\n"
        f"Root Cause: {c.get('root_cause_summary', 'N/A')}\n\n"
        "Action Required: Please correct the identified data issue and manually rerun the integration."
    )


def _comment_escalate(c: dict) -> str:
    return (
        "🚨 Integration Monitor — Escalation Required\n\n"
        f"Error Type: {c.get('error_type', 'UNKNOWN')}\n"
        f"Integration: {c.get('integration_name') or 'Unknown'}\n"
        "Priority: HIGH\n"
        f"Root Cause: {c.get('root_cause_summary', 'N/A')}\n\n"
        "@krishnagutta — This error requires immediate attention."
    )


def _comment_hold_investigate(c: dict) -> str:
    return (
        "🤖 Integration Monitor — Flagged for Review\n\n"
        f"Error Type: {c.get('error_type', 'UNKNOWN')}\n"
        f"Root Cause: {c.get('root_cause_summary', 'N/A')}\n\n"
        "Action: Auto-action withheld. This ticket has been flagged for manual review "
        "due to an unusual error pattern."
    )


COMMENT_BUILDERS = {
    "AUTO_RETRY": _comment_auto_retry,
    "CREATE_DATA_FIX_TASK": _comment_data_fix,
    "ESCALATE_IMMEDIATELY": _comment_escalate,
    "HOLD_FOR_REVIEW": _comment_hold_investigate,
    "INVESTIGATE": _comment_hold_investigate,
}


# ---------------------------------------------------------------------------
# Main run logic
# ---------------------------------------------------------------------------

def run(dry_run: bool, lookback_hours: int) -> None:
    logger = logging.getLogger("agent")
    logger.info(
        "Starting Integration Monitor | dry_run=%s | lookback=%dh | %s",
        dry_run,
        lookback_hours,
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    jira = JiraClient()

    # Step 1: Fetch open integration error tickets
    tickets = jira.get_open_integration_errors(lookback_hours)
    if not tickets:
        logger.info("✅ All clear — no open integration error tickets found.")
        post_digest([], dry_run)
        return

    logger.info("Processing %d ticket(s)...", len(tickets))
    results = []

    for ticket in tickets:
        issue_key = ticket["key"]
        fields = ticket.get("fields", {})
        summary = fields.get("summary", "")
        desc_raw = fields.get("description", "")
        description = desc_raw if desc_raw else ""

        ticket_url = jira.get_ticket_url(issue_key)
        logger.info("--- Processing %s: %s", issue_key, summary[:80])

        # Step 2: Classify
        classification = classify_error(issue_key, summary, description)
        action = classification.get("recommended_action", "INVESTIGATE")
        priority = classification.get("priority", "MEDIUM")
        error_type = classification.get("error_type", "UNKNOWN")

        logger.info(
            "Classified %s: %s → %s (priority=%s)",
            issue_key, error_type, action, priority,
        )

        # Step 3: Build comment
        comment_builder = COMMENT_BUILDERS.get(action, _comment_hold_investigate)
        comment = comment_builder(classification)

        # Step 4: Execute action
        jira.add_comment(issue_key, comment, dry_run)

        if action == "AUTO_RETRY":
            jira.transition_ticket(issue_key, "In Progress", dry_run)

        # Step 5: Notify Slack for HIGH priority or ESCALATE_IMMEDIATELY
        if priority == "HIGH" or action == "ESCALATE_IMMEDIATELY":
            notify_ticket_action(
                issue_key=issue_key,
                ticket_url=ticket_url,
                classification=classification,
                action_taken=action,
                dry_run=dry_run,
            )

        results.append(
            {
                "key": issue_key,
                "url": ticket_url,
                "action": action,
                "integration": classification.get("integration_name"),
                "priority": priority,
                "error_type": error_type,
            }
        )

    # Step 6: Post digest
    post_digest(results, dry_run)

    # Step 7: Summary log
    logger.info(
        "Run complete. Processed %d ticket(s): %s",
        len(results),
        ", ".join(f"{r['key']}={r['action']}" for r in results),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Lyft PTECH Integration Monitoring Agent"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=config.DRY_RUN,
        help="Classify and log without making any Jira/Slack changes",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=config.LOOKBACK_HOURS,
        metavar="N",
        help="Hours to look back for new tickets (default: %(default)s)",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, lookback_hours=args.lookback)


if __name__ == "__main__":
    main()
