"""
Modular templates foundation for SkillWeave Next Level.

Provides basic infrastructure for loading and combining templates.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from string import Template as StringTemplate


class Template:
    """Represents a reusable template."""
    
    def __init__(self, name: str, content: Dict[str, Any], template_type: str = "generic"):
        self.name = name
        self.content = content
        self.type = template_type
        self.variables = self._extract_variables(content)
    
    def _extract_variables(self, data: Any, prefix: str = "") -> List[str]:
        """Extract template variable names from content."""
        variables = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                variables.extend(self._extract_variables(value, f"{prefix}.{key}" if prefix else key))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                variables.extend(self._extract_variables(item, f"{prefix}[{i}]"))
        elif isinstance(data, str):
            # Simple variable detection: ${var_name}
            import re
            matches = re.findall(r'\$\{([^}]+)\}', data)
            variables.extend(matches)
        
        return variables
    
    def apply_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Apply variable substitution to template content."""
        def _apply(obj: Any, vars_dict: Dict[str, Any]) -> Any:
            if isinstance(obj, dict):
                return {k: _apply(v, vars_dict) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_apply(item, vars_dict) for item in obj]
            elif isinstance(obj, str):
                try:
                    # Use string.Template for safe substitution
                    template = StringTemplate(obj)
                    return template.safe_substitute(vars_dict)
                except:
                    return obj
            else:
                return obj
        
        return _apply(self.content, variables)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "name": self.name,
            "type": self.type,
            "content": self.content,
            "variables": self.variables
        }


class TemplateManager:
    """Manages templates in .skillweave/templates/ directory."""
    
    TEMPLATES_DIR = "templates"
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.templates_dir = self.project_root / ".skillweave" / self.TEMPLATES_DIR
    
    def ensure_templates_dir(self) -> None:
        """Ensure templates directory exists."""
        self.templates_dir.mkdir(exist_ok=True, parents=True)
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """List all available templates."""
        self.ensure_templates_dir()
        
        templates = []
        for template_file in self.templates_dir.glob("*.yaml"):
            try:
                with open(template_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                template = Template(
                    name=template_file.stem,
                    content=data.get("content", {}),
                    template_type=data.get("type", "generic")
                )
                
                templates.append({
                    "file": template_file.name,
                    "template": template.to_dict()
                })
            except:
                continue
        
        return templates
    
    def load_template(self, name: str) -> Optional[Template]:
        """Load a template by name."""
        template_file = self.templates_dir / f"{name}.yaml"
        if not template_file.exists():
            return None
        
        try:
            with open(template_file, 'r') as f:
                data = yaml.safe_load(f) or {}
            
            return Template(
                name=name,
                content=data.get("content", {}),
                template_type=data.get("type", "generic")
            )
        except:
            return None
    
    def save_template(self, template: Template) -> Path:
        """Save a template to file."""
        self.ensure_templates_dir()
        
        template_file = self.templates_dir / f"{template.name}.yaml"
        data = {
            "name": template.name,
            "type": template.type,
            "content": template.content,
            "variables": template.variables
        }
        
        with open(template_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        return template_file
    
    def create_template_from_example(self, name: str, example: Dict[str, Any], template_type: str = "generic") -> Template:
        """Create a template from an example dictionary."""
        template = Template(name, example, template_type)
        self.save_template(template)
        return template
    
    def combine_templates(self, template_names: List[str], output_name: str, strategy: str = "merge") -> Optional[Template]:
        """
        Combine multiple templates into a new template.
        
        Args:
            template_names: List of template names to combine
            output_name: Name for the combined template
            strategy: Combination strategy ("merge", "sequence", "nested")
        
        Returns:
            Combined template or None if any template not found
        """
        templates = []
        for name in template_names:
            template = self.load_template(name)
            if not template:
                return None
            templates.append(template)
        
        # Simple merge strategy: merge content dictionaries
        if strategy == "merge":
            combined_content = {}
            for template in templates:
                if isinstance(template.content, dict):
                    combined_content.update(template.content)
                else:
                    # For non-dict content, store in list
                    if "items" not in combined_content:
                        combined_content["items"] = []
                    combined_content["items"].append(template.content)
        
        # Sequence strategy: create a step sequence
        elif strategy == "sequence":
            combined_content = {
                "steps": [template.content for template in templates]
            }
        
        # Nested strategy: nest under a key based on template type
        elif strategy == "nested":
            combined_content = {}
            for template in templates:
                if template.type not in combined_content:
                    combined_content[template.type] = []
                combined_content[template.type].append(template.content)
        
        else:
            raise ValueError(f"Unknown combination strategy: {strategy}")
        
        combined_template = Template(output_name, combined_content, "combined")
        self.save_template(combined_template)
        return combined_template


def get_template_manager(project_root: Optional[str] = None) -> TemplateManager:
    """Get template manager for project root."""
    if project_root is None:
        project_root = os.getcwd()
    return TemplateManager(project_root)