import logging
import requests
from requests.auth import HTTPBasicAuth

import config

logger = logging.getLogger(__name__)


class JiraClient:
    def __init__(self):
        self.base_url = config.JIRA_BASE_URL.rstrip("/")
        self.auth = HTTPBasicAuth(config.JIRA_USERNAME, config.JIRA_API_TOKEN)
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def get_open_integration_errors(self, lookback_hours: int) -> list[dict]:
        """Fetch all Open bugs with label=integration_event created in the last N hours."""
        jql = (
            f'project = PTECH AND issuetype = Bug AND status = Open '
            f'AND labels = "integration_event" AND created >= "-{lookback_hours}h"'
        )
        url = f"{self.base_url}/rest/api/2/search"
        params = {
            "jql": jql,
            "maxResults": 100,
            "fields": "summary,description,status,priority,assignee,created,comment,labels,components",
        }
        logger.debug("Searching Jira with JQL: %s", jql)
        try:
            response = requests.get(url, params=params, auth=self.auth, headers=self.headers)
            logger.debug("Jira search response: %s %s", response.status_code, url)
            response.raise_for_status()
            data = response.json()
            issues = data.get("issues", [])
            logger.info("Found %d open integration error tickets", len(issues))
            return issues
        except requests.HTTPError as e:
            logger.error("Jira search failed: %s %s — %s", response.status_code, url, e)
            return []
        except Exception as e:
            logger.error("Unexpected error fetching Jira tickets: %s", e)
            return []

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Returns available transitions for a ticket."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        response = requests.get(url, auth=self.auth, headers=self.headers)
        logger.debug("Get transitions %s: %s", issue_key, response.status_code)
        response.raise_for_status()
        return response.json().get("transitions", [])

    def transition_ticket(self, issue_key: str, target_status: str, dry_run: bool) -> bool:
        """Finds the transition ID matching target_status and executes it."""
        try:
            transitions = self.get_transitions(issue_key)
        except Exception as e:
            logger.error("Could not fetch transitions for %s: %s", issue_key, e)
            return False

        match = next(
            (t for t in transitions if t["to"]["name"].lower() == target_status.lower()),
            None,
        )
        if not match:
            logger.warning(
                "No transition to '%s' found for %s. Available: %s",
                target_status,
                issue_key,
                [t["to"]["name"] for t in transitions],
            )
            return False

        if dry_run:
            logger.info("[DRY RUN] Would transition %s → %s (id=%s)", issue_key, target_status, match["id"])
            return True

        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        payload = {"transition": {"id": match["id"]}}
        response = requests.post(url, json=payload, auth=self.auth, headers=self.headers)
        logger.debug("Transition %s → %s: %s", issue_key, target_status, response.status_code)
        response.raise_for_status()
        logger.info("Transitioned %s → %s", issue_key, target_status)
        return True

    def add_comment(self, issue_key: str, comment: str, dry_run: bool) -> bool:
        """Adds a comment to a ticket."""
        if dry_run:
            logger.info("[DRY RUN] Would add comment to %s:\n%s", issue_key, comment[:200])
            return True

        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        payload = {"body": comment}
        response = requests.post(url, json=payload, auth=self.auth, headers=self.headers)
        logger.debug("Add comment %s: %s", issue_key, response.status_code)
        response.raise_for_status()
        logger.info("Added comment to %s", issue_key)
        return True

    def get_ticket_url(self, issue_key: str) -> str:
        """Returns the Jira browse URL for a ticket."""
        return f"{self.base_url}/browse/{issue_key}"
