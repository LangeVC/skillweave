"""
Tests for community know-how prototype.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import json
from pathlib import Path

from skillweave.persistence import SkillWeavePersistence, SkillWeaveConfig, RiskMode
from skillweave.community_knowhow import PatternExtractor, RepoCleanupRecommender


def test_pattern_extractor_no_logs():
    """Test pattern extraction with no tracking logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        extractor = PatternExtractor(persistence)
        
        result = extractor.extract_patterns()
        
        assert result["status"] == "no_logs"
        assert "No tracking logs" in result["message"]


def test_pattern_extractor_with_logs():
    """Test pattern extraction with sample tracking logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        
        # Create sample tracking logs
        sample_logs = [
            {
                "session_id": "test1",
                "skill": "blueprint",
                "status": "completed",
                "steps": [
                    {"name": "interview", "status": "completed"},
                    {"name": "prd_generation", "status": "completed"}
                ],
                "success": True
            },
            {
                "session_id": "test2",
                "skill": "promptchain",
                "status": "completed",
                "steps": [
                    {"name": "parse_sequence", "status": "completed"},
                    {"name": "validate", "status": "completed"}
                ],
                "success": True
            },
            {
                "session_id": "test3",
                "skill": "blueprint",
                "status": "failed",
                "steps": [
                    {"name": "interview", "status": "failed"}
                ],
                "success": False
            }
        ]
        
        # Save logs
        for log in sample_logs:
            persistence.save_tracking_log(log["session_id"], log)
        
        extractor = PatternExtractor(persistence)
        result = extractor.extract_patterns()
        
        assert result["status"] == "success"
        assert result["statistics"]["total_runs"] == 3
        assert result["statistics"]["successful_runs"] == 2
        assert result["statistics"]["success_rate"] == 0.67  # 2/3 rounded to 2 decimal places
        
        # Check patterns
        skills = [p["skill"] for p in result["patterns"]["most_common_skills"]]
        assert "blueprint" in skills
        assert "promptchain" in skills
        
        # Check recommendations
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)


def test_repo_cleanup_recommender():
    """Test repository cleanup recommendations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        test_dir = Path(tmpdir)
        
        # Create a large file
        large_file = test_dir / "large_file.bin"
        with open(large_file, "wb") as f:
            f.write(b"0" * 11 * 1024 * 1024)  # 11 MB
        
        # Create duplicate filenames
        (test_dir / "duplicate.txt").write_text("test")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "duplicate.txt").write_text("test2")
        
        # Create .env file
        (test_dir / ".env").write_text("SECRET=test")
        
        recommender = RepoCleanupRecommender(tmpdir)
        result = recommender.analyze_repository()
        
        assert result["status"] == "success"
        assert result["findings_count"] >= 2  # At least large files and env files
        
        # Check categories present
        categories = {f["category"] for f in result["findings"]}
        assert "large_files" in categories or "env_files" in categories
        
        # Check summary
        assert "summary" in result
        assert isinstance(result["summary"], str)


def test_repo_cleanup_no_issues():
    """Test repository cleanup with no issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal structure
        test_dir = Path(tmpdir)
        (test_dir / "README.md").write_text("# Test")
        
        recommender = RepoCleanupRecommender(tmpdir)
        result = recommender.analyze_repository()
        
        assert result["status"] == "success"
        # May still find temporary files or other patterns
        # But at least the function runs without error


def test_extract_community_patterns_function():
    """Test the standalone extract_community_patterns function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Need to create persistence with config to enable feature
        persistence = SkillWeavePersistence(tmpdir)
        config = SkillWeaveConfig(mode=RiskMode.MEDIUM)
        config.features["community_patterns"] = True
        persistence.save_config(config)
        
        # Import function after config is saved
        from skillweave.community_knowhow import extract_community_patterns
        
        result = extract_community_patterns(tmpdir)
        assert result["status"] == "no_logs"  # No logs yet


if __name__ == "__main__":
    test_pattern_extractor_no_logs()
    print("✓ test_pattern_extractor_no_logs")
    
    test_pattern_extractor_with_logs()
    print("✓ test_pattern_extractor_with_logs")
    
    test_repo_cleanup_recommender()
    print("✓ test_repo_cleanup_recommender")
    
    test_repo_cleanup_no_issues()
    print("✓ test_repo_cleanup_no_issues")
    
    test_extract_community_patterns_function()
    print("✓ test_extract_community_patterns_function")
    
    print("\nAll community know-how tests passed!")