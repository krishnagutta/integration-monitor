import os
from dotenv import load_dotenv

load_dotenv()


def get(key: str, default=None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return value


JIRA_BASE_URL = get("JIRA_BASE_URL", "https://jira.lyft.net")
JIRA_USERNAME = get("JIRA_USERNAME", required=True)
JIRA_API_TOKEN = get("JIRA_API_TOKEN", required=True)

# Lyft AI proxy — token format: "user:your-lyft-email@lyft.com"
LYFT_AI_PROXY_TOKEN = get("LYFT_AI_PROXY_TOKEN", required=True)

SLACK_BOT_TOKEN = get("SLACK_BOT_TOKEN")  # Optional — skips Slack if not set
SLACK_CHANNEL_ID = get("SLACK_CHANNEL_ID", "C09KBAUMZMJ")

LOOKBACK_HOURS = int(get("LOOKBACK_HOURS", "1"))
DRY_RUN = get("DRY_RUN", "false").lower() == "true"
