"""
Community know-how prototype for SkillWeave Next Level.

This module provides pattern extraction from successful runs and
repo cleanup recommendations as a proof-of-concept prototype.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
import yaml


class PatternExtractor:
    """Extract patterns from tracking logs."""
    
    def __init__(self, persistence):
        """
        Initialize with persistence instance.
        
        Args:
            persistence: SkillWeavePersistence instance
        """
        self.persistence = persistence
    
    def extract_patterns(self) -> Dict[str, Any]:
        """
        Extract patterns from tracking logs.
        
        Returns:
            Dictionary with extracted patterns and statistics.
        """
        logs = self.persistence.list_tracking_logs()
        if not logs:
            return {"status": "no_logs", "message": "No tracking logs found."}
        
        # Load log data
        log_data = []
        for log_info in logs:
            data = self.persistence.load_tracking_log(log_info["session_id"])
            if data:
                log_data.append(data)
        
        if not log_data:
            return {"status": "empty_logs", "message": "Log files empty or corrupted."}
        
        # Extract basic statistics
        skill_counter = Counter()
        step_counter = Counter()
        success_count = 0
        total_steps = 0
        
        for data in log_data:
            skill = data.get("skill", "unknown")
            skill_counter[skill] += 1
            
            steps = data.get("steps", [])
            total_steps += len(steps)
            for step in steps:
                if isinstance(step, dict):
                    step_name = step.get("name", "unknown")
                    step_counter[step_name] += 1
                else:
                    step_counter[str(step)] += 1
            
            # Determine success (simple heuristic)
            if data.get("status") == "completed" or data.get("success", False):
                success_count += 1
        
        total_runs = len(log_data)
        success_rate = success_count / total_runs if total_runs > 0 else 0
        
        # Identify common patterns
        common_steps = step_counter.most_common(5)
        common_skills = skill_counter.most_common(3)
        
        # Extract timing patterns if available
        avg_steps_per_run = total_steps / total_runs if total_runs > 0 else 0
        
        return {
            "status": "success",
            "statistics": {
                "total_runs": total_runs,
                "successful_runs": success_count,
                "success_rate": round(success_rate, 2),
                "total_steps_recorded": total_steps,
                "average_steps_per_run": round(avg_steps_per_run, 1),
            },
            "patterns": {
                "most_common_skills": [
                    {"skill": skill, "count": count} 
                    for skill, count in common_skills
                ],
                "most_common_steps": [
                    {"step": step, "count": count} 
                    for step, count in common_steps
                ],
            },
            "recommendations": self._generate_recommendations(
                skill_counter, step_counter, success_rate, total_runs
            )
        }
    
    def _generate_recommendations(self, skill_counter, step_counter, success_rate, total_runs):
        """Generate recommendations based on patterns."""
        recommendations = []
        
        # Skill usage recommendations
        if total_runs >= 3:
            most_common_skill, skill_count = skill_counter.most_common(1)[0]
            if skill_count / total_runs > 0.7:
                recommendations.append(
                    f"Skill '{most_common_skill}' is used in {int((skill_count/total_runs)*100)}% of runs. "
                    f"Consider creating a template for this workflow."
                )
        
        # Success rate recommendations
        if success_rate < 0.5 and total_runs >= 5:
            recommendations.append(
                f"Success rate is low ({int(success_rate*100)}%). "
                f"Review failed runs to identify common failure points."
            )
        
        # Step complexity recommendations
        if step_counter:
            avg_steps = sum(step_counter.values()) / len(step_counter)
            if avg_steps > 10:
                recommendations.append(
                    f"Workflows average {avg_steps:.1f} steps. Consider breaking down complex workflows."
                )
        
        return recommendations


class RepoCleanupRecommender:
    """Generate repository cleanup recommendations."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
    
    def analyze_repository(self) -> Dict[str, Any]:
        """
        Analyze repository for common cleanup opportunities.
        
        Returns:
            Dictionary with findings and recommendations.
        """
        findings = []
        
        # Check for large files
        large_files = self._find_large_files()
        if large_files:
            findings.append({
                "category": "large_files",
                "count": len(large_files),
                "files": large_files[:5],  # Limit to 5 examples
                "recommendation": "Consider compressing or removing large files."
            })
        
        # Check for duplicate files (by name)
        duplicate_names = self._find_duplicate_filenames()
        if duplicate_names:
            findings.append({
                "category": "duplicate_filenames",
                "count": len(duplicate_names),
                "examples": list(duplicate_names)[:5],
                "recommendation": "Files with duplicate names may cause confusion."
            })
        
        # Check for node_modules or other large dependencies
        dependency_dirs = self._find_large_dependency_dirs()
        if dependency_dirs:
            findings.append({
                "category": "large_dependency_dirs",
                "count": len(dependency_dirs),
                "directories": dependency_dirs,
                "recommendation": "Consider using .gitignore or dependency pruning."
            })
        
        # Check for .env files (potential security risk)
        env_files = list(self.project_root.glob("**/.env"))
        if env_files:
            findings.append({
                "category": "env_files",
                "count": len(env_files),
                "files": [str(f.relative_to(self.project_root)) for f in env_files],
                "recommendation": ".env files may contain secrets. Ensure they are in .gitignore."
            })
        
        # Check for temporary files
        temp_files = self._find_temp_files()
        if temp_files:
            findings.append({
                "category": "temporary_files",
                "count": len(temp_files),
                "examples": temp_files[:5],
                "recommendation": "Clean up temporary files."
            })
        
        return {
            "status": "success",
            "findings_count": len(findings),
            "findings": findings,
            "summary": self._generate_summary(findings)
        }
    
    def _find_large_files(self, threshold_mb: int = 10) -> List[Dict]:
        """Find files larger than threshold_mb."""
        large_files = []
        for file_path in self.project_root.glob("**/*"):
            if file_path.is_file():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                if size_mb > threshold_mb:
                    large_files.append({
                        "path": str(file_path.relative_to(self.project_root)),
                        "size_mb": round(size_mb, 1)
                    })
        return sorted(large_files, key=lambda x: x["size_mb"], reverse=True)
    
    def _find_duplicate_filenames(self) -> set:
        """Find files with duplicate names (case-insensitive)."""
        name_count = Counter()
        for file_path in self.project_root.glob("**/*"):
            if file_path.is_file():
                name_count[file_path.name.lower()] += 1
        
        return {name for name, count in name_count.items() if count > 1}
    
    def _find_large_dependency_dirs(self) -> List[str]:
        """Find common large dependency directories."""
        large_dirs = []
        common_deps = ["node_modules", "vendor", ".venv", "venv", "__pycache__", ".pytest_cache"]
        
        for dep in common_deps:
            dep_path = self.project_root / dep
            if dep_path.exists() and dep_path.is_dir():
                # Calculate size
                total_size = 0
                for file_path in dep_path.glob("**/*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                
                size_mb = total_size / (1024 * 1024)
                if size_mb > 50:  # 50 MB threshold
                    large_dirs.append(f"{dep} ({size_mb:.1f} MB)")
        
        return large_dirs
    
    def _find_temp_files(self) -> List[str]:
        """Find common temporary file patterns."""
        temp_patterns = ["*.tmp", "*.temp", "*.log", "*.bak", "*.swp", "*.swo"]
        temp_files = []
        
        for pattern in temp_patterns:
            for file_path in self.project_root.glob(f"**/{pattern}"):
                if file_path.is_file():
                    temp_files.append(str(file_path.relative_to(self.project_root)))
        
        return temp_files[:20]  # Limit results
    
    def _generate_summary(self, findings: List[Dict]) -> str:
        """Generate a summary of findings."""
        if not findings:
            return "Repository appears clean. No major issues found."
        
        total_issues = sum(f["count"] for f in findings)
        return f"Found {total_issues} potential cleanup opportunities across {len(findings)} categories."


def extract_community_patterns(project_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract community patterns from tracking logs.
    
    Args:
        project_root: Root directory of the project.
    
    Returns:
        Dictionary with patterns and statistics.
    """
    from .persistence import SkillWeavePersistence
    
    persistence = SkillWeavePersistence(project_root)
    extractor = PatternExtractor(persistence)
    return extractor.extract_patterns()


def analyze_repository_cleanup(project_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze repository for cleanup opportunities.
    
    Args:
        project_root: Root directory of the project.
    
    Returns:
        Dictionary with cleanup recommendations.
    """
    if project_root is None:
        project_root = os.getcwd()
    
    recommender = RepoCleanupRecommender(project_root)
    return recommender.analyze_repository()