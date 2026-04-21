#!/usr/bin/env python3
"""
Create GitHub Issues from SkillWeave Next Level PRD tasks.
"""

import json
import subprocess
import sys
from typing import Dict, Any, List
from pathlib import Path

def load_prd_tasks(prd_path: str = "prd-skillweave-next-level.json") -> List[Dict[str, Any]]:
    """Load tasks from PRD JSON file."""
    with open(prd_path, 'r') as f:
        data = json.load(f)
    return data.get("tasks", [])

def create_issue(task: Dict[str, Any]) -> bool:
    """Create a GitHub issue for a task."""
    title = f"{task['id']}: {task['title']} [{task['priority'].upper()}]"
    
    # Build issue body
    body_parts = []
    body_parts.append(f"## {task['title']}")
    body_parts.append("")
    body_parts.append(f"**Description**: {task['description']}")
    body_parts.append("")
    
    body_parts.append("### Acceptance Criteria")
    for criterion in task.get("acceptanceCriteria", []):
        body_parts.append(f"- [ ] {criterion}")
    body_parts.append("")
    
    body_parts.append("### Task Details")
    body_parts.append(f"- **ID**: {task['id']}")
    body_parts.append(f"- **Priority**: {task['priority']}")
    body_parts.append(f"- **Type**: {task['type']}")
    body_parts.append(f"- **Estimated Effort**: {task['estimatedEffort']} hours")
    body_parts.append(f"- **Complexity Points**: {task.get('complexityPoints', 'N/A')} (1 point = 2 hours)")
    
    if task.get('dependsOn'):
        body_parts.append(f"- **Depends On**: {', '.join(task['dependsOn'])}")
    
    body_parts.append("")
    body_parts.append("### Source")
    body_parts.append(f"This issue was generated from SkillWeave Next Level PRD (Task {task['id']}).")
    body_parts.append("Complexity points use Fibonacci sequence (1 point = 2 hours).")
    
    body = "\n".join(body_parts)
    
    # Map task types to existing labels
    type_label_map = {
        'infrastructure': 'enhancement',  # Use enhancement for infrastructure
        'feature': 'enhancement',
        'refactor': 'enhancement',
        'enhancement': 'enhancement',
        'testing': 'enhancement',  # Use enhancement for testing
        'documentation': 'documentation'
    }
    
    labels = [
        type_label_map.get(task['type'], 'enhancement'),
        "next-level",
        "v0.5.0"
    ]
    
    # Map priority to color or keep as is (we'll skip priority labels for now)
    # priority_label = f"priority-{task['priority']}"
    # We'll add priority to title instead
    
    # Create issue using GitHub CLI
    cmd = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--label", ",".join(labels)
    ]
    
    print(f"Creating issue: {title}")
    print(f"Labels: {', '.join(labels)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_url = result.stdout.strip()
        print(f"Created: {issue_url}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating issue: {e.stderr}")
        return False

def main():
    """Main function."""
    prd_path = "prd-skillweave-next-level.json"
    if not Path(prd_path).exists():
        print(f"PRD file not found: {prd_path}")
        sys.exit(1)
    
    tasks = load_prd_tasks(prd_path)
    print(f"Loaded {len(tasks)} tasks from PRD")
    
    created = 0
    for task in tasks:
        if create_issue(task):
            created += 1
    
    print(f"\nSuccessfully created {created}/{len(tasks)} issues")
    
    if created < len(tasks):
        print("Some issues may have failed to create. Check errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()