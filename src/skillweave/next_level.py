"""
Next Level integration module for SkillWeave.

Brings together all Next Level features: persistence, modes, checklist execution,
and design thinking lens.
"""

from typing import Dict, Any, List, Optional, Callable, Tuple, Literal
from pathlib import Path

from .persistence import SkillWeavePersistence, ensure_skillweave_folder, get_config, is_feature_enabled
from .checklist import ChecklistParser, ChecklistManager, Checklist
from .design_thinking import DesignThinkingLens
from .mode_manager import ModeManager, RiskMode
from .community_knowhow import PatternExtractor, RepoCleanupRecommender, extract_community_patterns, analyze_repository_cleanup
from .templates import TemplateManager
from .capability import CapabilityRouter, Capability, AgentType, get_capability_router, route_task
from .intelligent_detection import SkillDetectionOrchestrator, OnboardingFlowController, Skill


class SkillWeaveNextLevel:
    """
    Main integration class for SkillWeave Next Level features.
    
    Provides unified access to:
    - Persistent state management (.skillweave folder)
    - Three risk modes (conservative, medium, unicorn)
    - Checklist execution
    - Design thinking lens
    """
    
    def __init__(
        self, 
        project_root: Optional[str] = None,
        cli_risk_mode: Optional[Literal["conservative", "medium", "unicorn"]] = None,
        env_risk_mode: Optional[Literal["conservative", "medium", "unicorn"]] = None
    ):
        """
        Initialize Next Level features.
        
        Args:
            project_root: Root directory of the project. If None, uses current
                         working directory.
            cli_risk_mode: Risk mode from command-line override (highest precedence)
            env_risk_mode: Risk mode from environment variable override (second precedence)
        """
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.persistence = ensure_skillweave_folder(str(self.project_root))
        self.config = self.persistence.load_config()
        self.mode_manager = ModeManager(
            str(self.project_root), 
            cli_risk_mode=cli_risk_mode,
            env_risk_mode=env_risk_mode
        )
        self.checklist_manager = ChecklistManager(str(self.project_root))
        self.design_thinking = DesignThinkingLens(str(self.project_root))
        self.template_manager = TemplateManager(str(self.project_root))
        
    @classmethod
    def from_skill_args(
        cls, 
        project_root: Optional[str] = None, 
        skill_args: Optional[Dict[str, Any]] = None
    ) -> "SkillWeaveNextLevel":
        """
        Create SkillWeaveNextLevel instance from skill arguments.
        
        Args:
            project_root: Optional project root directory
            skill_args: Optional skill arguments dictionary (must contain 'risk_mode' key if override desired)
            
        Returns:
            SkillWeaveNextLevel instance
        """
        cli_risk_mode = skill_args.get('risk_mode') if skill_args else None
        return cls(project_root, cli_risk_mode=cli_risk_mode)
        
    def get_mode(self) -> RiskMode:
        """Get current risk mode."""
        return self.mode_manager.get_mode()
    
    def is_checklist_enabled(self) -> bool:
        """Check if checklist execution feature is enabled."""
        return is_feature_enabled("checklist_execution", str(self.project_root))
    
    def is_design_thinking_enabled(self) -> bool:
        """Check if design thinking lens feature is enabled."""
        return is_feature_enabled("design_thinking_lens", str(self.project_root))
    
    def is_community_knowhow_enabled(self) -> bool:
        """Check if community know-how feature is enabled."""
        return is_feature_enabled("community_patterns", str(self.project_root))
    
    def is_modular_templates_enabled(self) -> bool:
        """Check if modular templates feature is enabled."""
        return is_feature_enabled("modular_templates", str(self.project_root))
    
    def get_design_thinking_lens(self):
        """Get the design thinking lens instance."""
        return self.design_thinking
    
    def get_template_manager(self):
        """Get the template manager instance."""
        return self.template_manager
    
    def parse_checklist(self, markdown: str):
        """Parse markdown checklist."""
        return ChecklistParser.parse_markdown(markdown)
    
    def get_mode_guidance(self, skill_name: str) -> str:
        """
        Get mode-specific guidance for a skill.
        
        Args:
            skill_name: Name of skill (blueprint, promptchain, releasechain)
        
        Returns:
            Markdown string with guidance
        """
        return self.mode_manager.get_mode_guidance(skill_name)
    
    def should_require_approval(self, action_type: str) -> bool:
        """
        Determine if approval is required for an action.
        
        Args:
            action_type: Type of action (e.g., "destructive", "execution", "review")
        """
        return self.mode_manager.should_require_approval(action_type)
    
    def get_max_parallel_tasks(self) -> int:
        """Get maximum parallel tasks allowed for current mode."""
        return self.mode_manager.get_max_parallel_tasks()
    
    def process_with_checklist(
        self,
        content: str,
        executor_func: Callable[[str, int], bool],
        checklist_title: Optional[str] = None
    ) -> Tuple[str, bool]:
        """
        Process content that may contain a checklist.
        
        Args:
            content: Content that may contain markdown checklist
            executor_func: Function that executes a checklist item
                          Takes (item_text, item_id) and returns success
            checklist_title: Optional title for checklist section
        
        Returns:
            Tuple of (updated_content, checklist_completed)
        """
        # Check if checklist feature is enabled
        if not self.checklist_manager.is_enabled():
            return content, False
        
        # Try to find checklist in content
        checklist = self.checklist_manager.find_checklist_in_text(content)
        if not checklist:
            return content, False
        
        # Execute checklist if there are unchecked items
        if checklist.unchecked_items:
            updated_checklist, completed = self.checklist_manager.execute_checklist_loop(
                checklist, executor_func
            )
            
            # Generate markdown with progress
            checklist_markdown = ChecklistParser.markdown_with_progress(updated_checklist)
            
            # Insert or replace checklist in content
            if checklist_title:
                checklist_section = f"\n\n## {checklist_title}\n\n{checklist_markdown}"
            else:
                checklist_section = f"\n\n## Checklist Progress\n\n{checklist_markdown}"
            
            # Simple replacement: look for existing checklist pattern
            lines = content.split('\n')
            checklist_start = -1
            checklist_end = -1
            
            for i, line in enumerate(lines):
                if line.strip().startswith('- [ ]') or line.strip().startswith('- [x]'):
                    if checklist_start == -1:
                        checklist_start = i
                    checklist_end = i
                elif checklist_start != -1 and not line.strip().startswith('-') and line.strip() != '':
                    # End of checklist
                    break
            
            if checklist_start != -1 and checklist_end != -1:
                # Replace existing checklist
                lines[checklist_start:checklist_end + 1] = checklist_section.split('\n')
                updated_content = '\n'.join(lines)
            else:
                # Append checklist section
                updated_content = content + checklist_section
            
            return updated_content, completed
        
        return content, True  # Already completed
    
    def apply_design_thinking(
        self,
        skill_name: str,
        content: str,
        content_type: str = "text"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Apply design thinking lens to content.
        
        Args:
            skill_name: Name of skill (blueprint, promptchain, releasechain)
            content: Content to analyze
            content_type: Type of content (text, ui, architecture, etc.)
        
        Returns:
            Tuple of (content_with_feedback, analysis_result)
        """
        analysis_result = self.design_thinking.apply_to_content(
            skill_name, content, content_type
        )
        
        if not analysis_result.get("enabled", False):
            return content, analysis_result
        
        feedback_markdown = self.design_thinking.generate_markdown_feedback(analysis_result)
        if feedback_markdown:
            # Append feedback to content
            content_with_feedback = content + "\n\n" + feedback_markdown
            return content_with_feedback, analysis_result
        
        return content, analysis_result
    
    def extract_community_patterns(self) -> Dict[str, Any]:
        """
        Extract community patterns from tracking logs.
        
        Returns:
            Dictionary with patterns and statistics
        """
        # Check if community patterns feature is enabled
        if not is_feature_enabled("community_patterns", str(self.project_root)):
            return {
                "status": "disabled",
                "message": "Community patterns feature is disabled. Enable in config.yaml."
            }
        
        extractor = PatternExtractor(self.persistence)
        return extractor.extract_patterns()
    
    def analyze_repository_cleanup(self) -> Dict[str, Any]:
        """
        Analyze repository for cleanup opportunities.
        
        Returns:
            Dictionary with cleanup recommendations
        """
        # Check if community patterns feature is enabled
        if not is_feature_enabled("community_patterns", str(self.project_root)):
            return {
                "status": "disabled",
                "message": "Community patterns feature is disabled. Enable in config.yaml."
            }
        
        recommender = RepoCleanupRecommender(str(self.project_root))
        return recommender.analyze_repository()
    
    def get_template_manager(self) -> Optional[TemplateManager]:
        """
        Get template manager if modular templates feature is enabled.
        
        Returns:
            TemplateManager instance or None if feature disabled
        """
        if not is_feature_enabled("modular_templates", str(self.project_root)):
            return None
        return TemplateManager(str(self.project_root))
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """
        List available templates.
        
        Returns:
            List of template metadata dictionaries
        """
        manager = self.get_template_manager()
        if not manager:
            return []
        return manager.list_templates()
    
    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load a template by name.
        
        Returns:
            Template dictionary or None if not found or feature disabled
        """
        manager = self.get_template_manager()
        if not manager:
            return None
        
        template = manager.load_template(name)
        if not template:
            return None
        
        return template.to_dict()
    
    def is_capability_routing_enabled(self) -> bool:
        """Check if capability-based routing feature is enabled."""
        return is_feature_enabled("capability_routing", str(self.project_root))

    def get_capability_router(self):
        """Get capability router if feature enabled."""
        if not self.is_capability_routing_enabled():
            return None
        from .capability import get_capability_router
        return get_capability_router(str(self.project_root))

    def route_task(self, capability: str, preferences: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Route a task to an agent based on capability."""
        if not self.is_capability_routing_enabled():
            return None
        router = self.get_capability_router()
        if not router:
            return None
        from .capability import route_task as route_task_func
        return route_task_func(capability, str(self.project_root), preferences)
    
    def get_project_status(self) -> Dict[str, Any]:
        """
        Get comprehensive project status.
        
        Returns:
            Dictionary with project status information
        """
        # Load tracking logs
        tracking_logs = self.persistence.list_tracking_logs()
        
        # Get checklist progress if available
        checklist_progress = 0.0
        checklist_completed = True
        
        # We would need to scan for checklist files, but for now placeholder
        
        return {
            "mode": self.get_mode().value,
            "features_enabled": {
                "checklist_execution": is_feature_enabled("checklist_execution", str(self.project_root)),
                "design_thinking_lens": is_feature_enabled("design_thinking_lens", str(self.project_root)),
                "community_patterns": is_feature_enabled("community_patterns", str(self.project_root)),
                "modular_templates": is_feature_enabled("modular_templates", str(self.project_root)),
                "capability_routing": is_feature_enabled("capability_routing", str(self.project_root)),
            },
            "tracking_logs_count": len(tracking_logs),
            "recent_logs": tracking_logs[:5],  # Last 5 logs
            "checklist_progress": checklist_progress,
            "checklist_completed": checklist_completed,
            "project_root": str(self.project_root),
        }
    
    def create_handover_document(
        self,
        skill_name: str,
        task_description: str,
        outcomes: Dict[str, Any],
        next_steps: Optional[str] = None
    ) -> Path:
        """
        Create a handover document in .skillweave/handover/
        
        Args:
            skill_name: Name of skill that created the document
            task_description: Description of the task
            outcomes: Dictionary with outcomes, results, or state
            next_steps: Optional next steps for handover
        
        Returns:
            Path to created handover document
        """
        import json
        from datetime import datetime
        
        handover_dir = self.persistence.skillweave_dir / "handover"
        handover_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"handover-{skill_name}-{timestamp}.md"
        filepath = handover_dir / filename
        
        content = []
        content.append(f"# Handover Document: {skill_name}")
        content.append(f"**Created**: {datetime.now().isoformat()}")
        content.append(f"**Mode**: {self.get_mode().value}")
        content.append("")
        
        content.append("## Task Description")
        content.append(task_description)
        content.append("")
        
        content.append("## Outcomes")
        for key, value in outcomes.items():
            if isinstance(value, dict):
                content.append(f"### {key}")
                for subkey, subvalue in value.items():
                    content.append(f"- **{subkey}**: {subvalue}")
            else:
                content.append(f"- **{key}**: {value}")
        content.append("")
        
        if next_steps:
            content.append("## Next Steps")
            content.append(next_steps)
            content.append("")
        
        content.append("## Project Status")
        status = self.get_project_status()
        content.append(f"- **Mode**: {status['mode']}")
        content.append(f"- **Checklist Execution**: {'Enabled' if status['features_enabled']['checklist_execution'] else 'Disabled'}")
        content.append(f"- **Design Thinking Lens**: {'Enabled' if status['features_enabled']['design_thinking_lens'] else 'Disabled'}")
        content.append("")
        
        content.append("## Configuration")
        content.append("```yaml")
        import yaml
        content.append(yaml.dump(self.config.to_dict(), default_flow_style=False))
        content.append("```")
        
        filepath.write_text("\n".join(content))
        return filepath
    
    def update_project_manifesto(self, updates: Dict[str, Any]) -> Path:
        """
        Update project manifesto with custom rules or settings.
        
        Args:
            updates: Dictionary with manifesto updates
        
        Returns:
            Path to manifesto file
        """
        import yaml
        
        manifesto_dir = self.persistence.skillweave_dir / "manifesto"
        manifesto_dir.mkdir(exist_ok=True)
        
        manifesto_file = manifesto_dir / "project-manifesto.yaml"
        
        # Load existing or create new
        if manifesto_file.exists():
            with open(manifesto_file, 'r') as f:
                existing = yaml.safe_load(f) or {}
        else:
            existing = {
                "mode_explanation": {
                    "conservative": "Maximum safety, security, and reliability",
                    "medium": "Balanced approach between safety and productivity",
                    "unicorn": "Maximum creativity, speed, and innovation",
                },
                "project_constraints": [],
                "design_principles": [],
                "custom_rules": [],
            }
        
        # Merge updates
        for key, value in updates.items():
            if isinstance(value, dict) and key in existing and isinstance(existing[key], dict):
                existing[key].update(value)
            elif isinstance(value, list) and key in existing and isinstance(existing[key], list):
                existing[key].extend(value)
            else:
                existing[key] = value
        
        # Save
        with open(manifesto_file, 'w') as f:
            yaml.dump(existing, f, default_flow_style=False, sort_keys=False)
        
        return manifesto_file