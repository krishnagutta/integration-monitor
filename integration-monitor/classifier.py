import json
import logging

import anthropic

import config

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an expert Workday integration support engineer at Lyft. Your job is to analyze Workday integration error tickets and classify them so an automated agent can take the right action.

Integration types you'll see:
- Workday EIB / Studio integrations
- Workday → ADP Payroll feeds
- Workday → Benefits vendors (Aetna, Fidelity, MetLife, Rightway)
- Workday → Checkr background checks
- Workday → GoodTime scheduling
- Workday → FreeNow (European payroll, ~900 employees across 10 countries, March 2026 go-live)
- Workday → Anaplan (headcount/finance)

Respond ONLY with a valid JSON object. No markdown, no explanation, no code fences.

JSON schema:
{
  "error_type": "<TRANSIENT | DATA_VALIDATION | AUTH_FAILURE | VOLUME_ANOMALY | PARTIAL_FAILURE | UNKNOWN>",
  "integration_name": "<name of the integration if identifiable, else null>",
  "affected_records": "<count or description if mentioned, else null>",
  "root_cause_summary": "<1-2 sentence plain English summary>",
  "recommended_action": "<AUTO_RETRY | CREATE_DATA_FIX_TASK | ESCALATE_IMMEDIATELY | HOLD_FOR_REVIEW | INVESTIGATE>",
  "auto_retry_safe": <true | false>,
  "priority": "<HIGH | MEDIUM | LOW>",
  "suggested_comment": "<professional comment to add to the Jira ticket explaining what the agent found and what action is being taken>"
}

Error type definitions:
- TRANSIENT: Connection timeout, network blip, temporary unavailability — safe to retry
- DATA_VALIDATION: Missing required field, invalid format, bad employee data
- AUTH_FAILURE: SFTP credentials failed, API token expired, certificate issue
- VOLUME_ANOMALY: Expected records but got 0 or dramatically fewer — do NOT auto-retry
- PARTIAL_FAILURE: Most records processed but some failed
- UNKNOWN: Cannot determine from available info

Action definitions:
- AUTO_RETRY: Safe to trigger a rerun immediately
- CREATE_DATA_FIX_TASK: Data needs human correction before rerun
- ESCALATE_IMMEDIATELY: Critical issue, alert @krishnagutta immediately
- HOLD_FOR_REVIEW: Unusual, flag for human review before acting
- INVESTIGATE: Need more context before acting"""

_FALLBACK = {
    "error_type": "UNKNOWN",
    "integration_name": None,
    "affected_records": None,
    "root_cause_summary": "Could not classify — Claude returned an unparseable response.",
    "recommended_action": "INVESTIGATE",
    "auto_retry_safe": False,
    "priority": "MEDIUM",
    "suggested_comment": "🤖 Integration Monitor — Classification failed. Raw response logged for manual review.",
}


def classify_error(issue_key: str, summary: str, description: str) -> dict:
    """Use Claude to classify a Jira integration error ticket."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    description_text = description if description else "No description provided."
    user_message = (
        f"Ticket: {issue_key}\n"
        f"Summary: {summary}\n\n"
        f"Description: {description_text}\n\n"
        "Classify this error and recommend action."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        logger.debug("Claude raw response for %s: %s", issue_key, raw[:300])

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            # Remove first line (```json or ```) and last line (```)
            raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            raw = raw.strip()

        result = json.loads(raw)
        logger.info(
            "Classified %s: %s → %s",
            issue_key,
            result.get("error_type", "?"),
            result.get("recommended_action", "?"),
        )
        return result

    except json.JSONDecodeError as e:
        logger.error("JSON parse error for %s: %s. Raw: %s", issue_key, e, raw[:500])
        return _FALLBACK.copy()
    except anthropic.APIError as e:
        logger.error("Anthropic API error for %s: %s", issue_key, e)
        return _FALLBACK.copy()
    except Exception as e:
        logger.error("Unexpected error classifying %s: %s", issue_key, e)
        return _FALLBACK.copy()
