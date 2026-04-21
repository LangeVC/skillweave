"""
GitHub Issues backlog synchronization for SkillWeave Next Level.

This module synchronizes GitHub issues with .skillweave tracking,
providing backlog management and progress tracking.
"""

import subprocess
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .persistence import SkillWeavePersistence


def run_gh_api(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
    """
    Run GitHub CLI API command.
    
    Args:
        endpoint: GitHub API endpoint (e.g., "repos/:owner/:repo/issues")
        method: HTTP method (GET, POST, PATCH)
        data: Optional JSON data for POST/PATCH requests
        
    Returns:
        API response as dictionary
    """
    cmd = ["gh", "api", endpoint, "--method", method]
    if data:
        cmd.extend(["--input", "-"])
    
    try:
        if data:
            # Pass JSON via stdin
            input_data = json.dumps(data).encode()
            result = subprocess.run(
                cmd, 
                input=input_data,
                capture_output=True, 
                text=False,  # Keep as bytes for input
                check=True
            )
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if result.stdout:
            return json.loads(result.stdout)
        return {}
    except subprocess.CalledProcessError as e:
        print(f"GitHub API error: {e.stderr}")
        raise
    except json.JSONDecodeError as e:
        print(f"Failed to parse GitHub API response: {e}")
        raise


def get_repo_owner_and_name() -> tuple[str, str]:
    """
    Get repository owner and name from git remote.
    
    Returns:
        Tuple of (owner, repo_name)
    """
    try:
        # Get remote URL
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True
        )
        url = result.stdout.strip()
        
        # Parse GitHub URL (supports both HTTPS and SSH)
        if url.startswith("https://github.com/"):
            parts = url.removeprefix("https://github.com/").removesuffix(".git").split("/")
        elif url.startswith("git@github.com:"):
            parts = url.removeprefix("git@github.com:").removesuffix(".git").split("/")
        else:
            raise ValueError(f"Unsupported remote URL format: {url}")
        
        if len(parts) >= 2:
            return parts[0], parts[1]
        else:
            raise ValueError(f"Could not parse owner/repo from URL: {url}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to get git remote: {e}")
        # Fallback to environment or default
        return "typelicious", "SkillWeave"


def fetch_github_issues(state: str = "open") -> List[Dict[str, Any]]:
    """
    Fetch issues from GitHub repository.
    
    Args:
        state: Issue state ("open", "closed", "all")
        
    Returns:
        List of issue dictionaries
    """
    owner, repo = get_repo_owner_and_name()
    endpoint = f"repos/{owner}/{repo}/issues"
    
    params = {
        "state": state,
        "per_page": 100,  # Max per page
        "page": 1
    }
    
    # Add query parameters
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    endpoint = f"{endpoint}?{query_string}"
    
    issues = run_gh_api(endpoint)
    
    # Filter out pull requests (issues have pull_request field if they're PRs)
    return [issue for issue in issues if "pull_request" not in issue]


def normalize_issue_for_backlog(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize GitHub issue data for backlog format.
    
    Args:
        issue: Raw GitHub issue data
        
    Returns:
        Normalized backlog item
    """
    # Extract relevant fields
    labels = [label["name"] for label in issue.get("labels", [])]
    
    # Try to extract task ID from title (format "ID: Title")
    task_id = None
    title = issue["title"]
    if ": " in title:
        possible_id = title.split(": ")[0]
        if "-" in possible_id:  # e.g., ARCH-001
            task_id = possible_id
    
    # Try to extract complexity points from body
    complexity_points = None
    if "Complexity Points:" in issue.get("body", ""):
        import re
        match = re.search(r"Complexity Points:\s*(\d+)", issue.get("body", ""))
        if match:
            complexity_points = int(match.group(1))
    
    return {
        "id": task_id or f"ISSUE-{issue['number']}",
        "github_id": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "url": issue["html_url"],
        "labels": labels,
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "closed_at": issue.get("closed_at"),
        "assignee": issue.get("assignee", {}).get("login") if issue.get("assignee") else None,
        "milestone": issue.get("milestone", {}).get("title") if issue.get("milestone") else None,
        "complexity_points": complexity_points,
        "body_preview": issue.get("body", "")[:500] if issue.get("body") else ""
    }


def sync_backlog_to_specs(persistence: SkillWeavePersistence) -> Path:
    """
    Synchronize GitHub issues to .skillweave/specs/backlog.yaml.
    
    Args:
        persistence: SkillWeavePersistence instance
        
    Returns:
        Path to saved backlog file
    """
    print("Fetching GitHub issues...")
    issues = fetch_github_issues(state="all")  # Get both open and closed
    
    print(f"Found {len(issues)} issues")
    
    # Normalize issues
    backlog_items = [normalize_issue_for_backlog(issue) for issue in issues]
    
    # Sort by GitHub ID (newest first)
    backlog_items.sort(key=lambda x: x["github_id"], reverse=True)
    
    # Prepare backlog data
    backlog_data = {
        "synced_at": datetime.now().isoformat(),
        "repo": list(get_repo_owner_and_name()),  # Convert tuple to list for YAML serialization
        "total_issues": len(backlog_items),
        "open_issues": len([i for i in backlog_items if i["state"] == "open"]),
        "closed_issues": len([i for i in backlog_items if i["state"] == "closed"]),
        "items": backlog_items
    }
    
    # Ensure specs directory exists
    specs_dir = persistence.skillweave_dir / "specs"
    specs_dir.mkdir(exist_ok=True, parents=True)
    
    # Save to YAML
    backlog_path = specs_dir / "backlog.yaml"
    with open(backlog_path, "w") as f:
        yaml.dump(backlog_data, f, default_flow_style=False, sort_keys=False)
    
    print(f"Backlog saved to {backlog_path}")
    return backlog_path


def update_tracking_from_backlog(persistence: SkillWeavePersistence) -> None:
    """
    Update tracking logs based on backlog status.
    
    For each closed issue in backlog, ensure there's a tracking log entry
    marking the task as complete.
    
    Args:
        persistence: SkillWeavePersistence instance
    """
    # Load backlog
    backlog_path = persistence.skillweave_dir / "specs" / "backlog.yaml"
    if not backlog_path.exists():
        print("Backlog file not found, skipping tracking update")
        return
    
    with open(backlog_path, "r") as f:
        backlog = yaml.safe_load(f)
    
    if not backlog or "items" not in backlog:
        print("No items in backlog, skipping tracking update")
        return
    
    # Find closed issues that are Next Level tasks
    next_level_closed = [
        item for item in backlog["items"]
        if item["state"] == "closed" 
        and any(label in item["labels"] for label in ["next-level", "v0.5.0"])
    ]
    
    if not next_level_closed:
        print("No closed Next Level issues found")
        return
    
    # For each closed Next Level issue, create or update tracking log
    for item in next_level_closed:
        task_id = item["id"]
        
        # Check if tracking log already exists for this task
        existing_log = persistence.load_tracking_log(f"issue-{task_id}")
        if existing_log:
            # Log already exists, ensure it's marked complete
            if existing_log.get("status") != "completed":
                existing_log["status"] = "completed"
                existing_log["completed_at"] = item["closed_at"] or datetime.now().isoformat()
                persistence.save_tracking_log(f"issue-{task_id}", existing_log)
                print(f"Updated tracking log for {task_id}")
        else:
            # Create new tracking log entry
            log_data = {
                "task_id": task_id,
                "github_issue": item["github_id"],
                "title": item["title"],
                "status": "completed",
                "completed_at": item["closed_at"] or datetime.now().isoformat(),
                "synced_at": datetime.now().isoformat(),
                "labels": item["labels"]
            }
            persistence.save_tracking_log(f"issue-{task_id}", log_data)
            print(f"Created tracking log for {task_id}")


def sync_backlog(project_root: Optional[str] = None) -> None:
    """
    Main synchronization function.
    
    Fetches GitHub issues, saves to backlog, and updates tracking logs.
    
    Args:
        project_root: Optional project root directory (defaults to current directory)
    """
    persistence = SkillWeavePersistence(project_root)
    
    # Ensure .skillweave folder structure exists
    persistence.ensure_folder_structure()
    
    # Sync backlog
    backlog_path = sync_backlog_to_specs(persistence)
    
    # Update tracking logs based on backlog
    update_tracking_from_backlog(persistence)
    
    print(f"\nBacklog synchronization complete")
    print(f"- Backlog file: {backlog_path}")
    print(f"- Total issues synced: {len(persistence.list_tracking_logs())} tracking logs updated")


if __name__ == "__main__":
    sync_backlog()