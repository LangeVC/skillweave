"""
Tests for backlog_sync module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import pytest

from skillweave.backlog_sync import (
    run_gh_api,
    get_repo_owner_and_name,
    fetch_github_issues,
    normalize_issue_for_backlog,
    sync_backlog_to_specs,
    update_tracking_from_backlog,
    sync_backlog
)
from skillweave.persistence import SkillWeavePersistence


def test_run_gh_api_success():
    """Test run_gh_api with successful response."""
    mock_response = {"id": 1, "title": "Test Issue"}
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_response),
            stderr="",
            returncode=0
        )
        
        result = run_gh_api("repos/owner/repo/issues")
        
        assert result == mock_response
        mock_run.assert_called_once()


def test_run_gh_api_with_data():
    """Test run_gh_api with POST data."""
    mock_response = {"id": 2}
    test_data = {"title": "New Issue"}
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_response),
            stderr="",
            returncode=0
        )
        
        result = run_gh_api("repos/owner/repo/issues", method="POST", data=test_data)
        
        assert result == mock_response
        # Check that input was passed correctly
        call_args = mock_run.call_args
        assert "--input" in call_args[0][0]
        assert "-" in call_args[0][0]


def test_get_repo_owner_and_name_https():
    """Test get_repo_owner_and_name with HTTPS URL."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="https://github.com/LangeVC/skillweave.git\n",
            stderr="",
            returncode=0
        )
        
        owner, repo = get_repo_owner_and_name()
        
        assert owner == "LangeVC"
        assert repo == "skillweave"


def test_get_repo_owner_and_name_ssh():
    """Test get_repo_owner_and_name with SSH URL."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="git@github.com:LangeVC/skillweave.git\n",
            stderr="",
            returncode=0
        )
        
        owner, repo = get_repo_owner_and_name()
        
        assert owner == "LangeVC"
        assert repo == "skillweave"


def test_fetch_github_issues():
    """Test fetch_github_issues."""
    mock_issues = [
        {"number": 1, "title": "Issue 1", "state": "open", "labels": [], "created_at": "2024-01-01"},
        {"number": 2, "title": "Issue 2", "state": "closed", "labels": [], "created_at": "2024-01-02", "pull_request": {}}  # This is a PR
    ]
    
    with patch("skillweave.backlog_sync.run_gh_api") as mock_api, \
         patch("skillweave.backlog_sync.get_repo_owner_and_name") as mock_get_repo:
        mock_api.return_value = mock_issues
        mock_get_repo.return_value = ("LangeVC", "skillweave")
        
        issues = fetch_github_issues()
        
        # Should filter out PRs
        assert len(issues) == 1
        assert issues[0]["number"] == 1


def test_normalize_issue_for_backlog():
    """Test normalize_issue_for_backlog."""
    raw_issue = {
        "number": 42,
        "title": "ARCH-001: Test Issue [HIGH]",
        "state": "open",
        "html_url": "https://github.com/owner/repo/issues/42",
        "labels": [{"name": "enhancement"}, {"name": "next-level"}],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "closed_at": None,
        "assignee": None,
        "milestone": None,
        "body": "Description\nComplexity Points: 3\nMore details"
    }
    
    normalized = normalize_issue_for_backlog(raw_issue)
    
    assert normalized["id"] == "ARCH-001"
    assert normalized["github_id"] == 42
    assert normalized["title"] == raw_issue["title"]
    assert normalized["state"] == "open"
    assert normalized["url"] == raw_issue["html_url"]
    assert normalized["labels"] == ["enhancement", "next-level"]
    assert normalized["complexity_points"] == 3


def test_normalize_issue_no_complexity():
    """Test normalize_issue_for_backlog without complexity points."""
    raw_issue = {
        "number": 43,
        "title": "Some Issue",
        "state": "closed",
        "html_url": "https://github.com/owner/repo/issues/43",
        "labels": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "closed_at": "2024-01-03T00:00:00Z",
        "assignee": None,
        "milestone": None,
        "body": "No complexity points here"
    }
    
    normalized = normalize_issue_for_backlog(raw_issue)
    
    assert normalized["id"] == "ISSUE-43"
    assert normalized["complexity_points"] is None
    assert normalized["state"] == "closed"


def test_sync_backlog_to_specs():
    """Test sync_backlog_to_specs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        mock_issues = [
            {
                "number": 1,
                "title": "ARCH-001: Test",
                "state": "open",
                "html_url": "https://example.com/1",
                "labels": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "closed_at": None,
                "assignee": None,
                "milestone": None,
                "body": "Complexity Points: 2"
            }
        ]
        
        with patch("skillweave.backlog_sync.fetch_github_issues") as mock_fetch:
            with patch("skillweave.backlog_sync.get_repo_owner_and_name") as mock_repo:
                mock_fetch.return_value = mock_issues
                mock_repo.return_value = ("owner", "repo")
                
                backlog_path = sync_backlog_to_specs(persistence)
                
                assert backlog_path.exists()
                
                # Load and verify backlog
                with open(backlog_path, "r") as f:
                    backlog = yaml.safe_load(f)
                
                assert backlog["repo"] == ["owner", "repo"]
                assert backlog["total_issues"] == 1
                assert backlog["open_issues"] == 1
                assert backlog["closed_issues"] == 0
                assert len(backlog["items"]) == 1
                
                item = backlog["items"][0]
                assert item["id"] == "ARCH-001"
                assert item["github_id"] == 1
                assert item["complexity_points"] == 2


def test_update_tracking_from_backlog_no_file():
    """Test update_tracking_from_backlog when backlog file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Should not raise error
        update_tracking_from_backlog(persistence)


def test_update_tracking_from_backlog_empty():
    """Test update_tracking_from_backlog with empty backlog."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Create empty backlog file
        backlog_path = persistence.skillweave_dir / "specs" / "backlog.yaml"
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(backlog_path, "w") as f:
            yaml.dump({"items": []}, f)
        
        # Should not raise error
        update_tracking_from_backlog(persistence)


def test_update_tracking_from_backlog_with_closed_issues():
    """Test update_tracking_from_backlog with closed Next Level issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Create backlog with closed Next Level issue
        backlog_data = {
            "synced_at": "2024-01-01T00:00:00Z",
            "repo": ["owner", "repo"],
            "items": [
                {
                    "id": "ARCH-001",
                    "github_id": 1,
                    "title": "Test Issue",
                    "state": "closed",
                    "labels": ["next-level", "v0.5.0"],
                    "closed_at": "2024-01-02T00:00:00Z"
                },
                {
                    "id": "OTHER-001",
                    "github_id": 2,
                    "title": "Other Issue",
                    "state": "closed",
                    "labels": ["bug"],  # Not Next Level
                    "closed_at": "2024-01-02T00:00:00Z"
                }
            ]
        }
        
        backlog_path = persistence.skillweave_dir / "specs" / "backlog.yaml"
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(backlog_path, "w") as f:
            yaml.dump(backlog_data, f)
        
        update_tracking_from_backlog(persistence)
        
        # Check that tracking log was created for ARCH-001
        tracking_log = persistence.load_tracking_log("issue-ARCH-001")
        assert tracking_log is not None
        assert tracking_log["task_id"] == "ARCH-001"
        assert tracking_log["status"] == "completed"
        assert tracking_log["github_issue"] == 1
        
        # Check that no tracking log was created for OTHER-001 (not Next Level)
        assert persistence.load_tracking_log("issue-OTHER-001") is None


def test_sync_backlog_integration():
    """Integration test for sync_backlog."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("skillweave.backlog_sync.fetch_github_issues") as mock_fetch:
            with patch("skillweave.backlog_sync.get_repo_owner_and_name") as mock_repo:
                mock_fetch.return_value = []
                mock_repo.return_value = ("owner", "repo")
                
                # Should not raise error
                sync_backlog(tmpdir)
                
                # Check that .skillweave folder was created
                skillweave_dir = Path(tmpdir) / ".skillweave"
                assert skillweave_dir.exists()
                assert (skillweave_dir / "specs" / "backlog.yaml").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])