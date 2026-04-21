"""
Checklist execution module for SkillWeave Next Level.

Supports markdown checklist parsing, state tracking, and loop execution.
"""

import re
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path

from .persistence import SkillWeavePersistence, ensure_skillweave_folder, is_feature_enabled


class ChecklistItemStatus(str, Enum):
    """Status of a checklist item."""
    UNCHECKED = "unchecked"
    IN_PROGRESS = "in_progress"
    CHECKED = "checked"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ChecklistItem:
    """Represents a single checklist item."""
    id: int
    text: str
    status: ChecklistItemStatus = ChecklistItemStatus.UNCHECKED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChecklistItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            text=data["text"],
            status=ChecklistItemStatus(data.get("status", "unchecked")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Checklist:
    """Represents a complete checklist."""
    items: List[ChecklistItem]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_hash(self) -> str:
        """Generate a hash for the checklist content."""
        content = "|".join(item.text for item in self.items)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed": self.completed,
            "metadata": self.metadata,
            "hash": self.get_hash(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checklist":
        """Create from dictionary."""
        items = [ChecklistItem.from_dict(item_data) for item_data in data["items"]]
        return cls(
            items=items,
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            completed=data.get("completed", False),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def unchecked_items(self) -> List[ChecklistItem]:
        """Get all unchecked items."""
        return [item for item in self.items if item.status == ChecklistItemStatus.UNCHECKED]
    
    @property
    def checked_items(self) -> List[ChecklistItem]:
        """Get all checked items."""
        return [item for item in self.items if item.status == ChecklistItemStatus.CHECKED]
    
    @property
    def progress(self) -> float:
        """Get progress percentage (0-100)."""
        if not self.items:
            return 100.0
        checked = len(self.checked_items)
        return (checked / len(self.items)) * 100
    
    def mark_checked(self, item_id: int, error: Optional[str] = None) -> None:
        """Mark an item as checked."""
        for item in self.items:
            if item.id == item_id:
                if error:
                    item.status = ChecklistItemStatus.FAILED
                    item.error = error
                else:
                    item.status = ChecklistItemStatus.CHECKED
                    item.completed_at = datetime.now().isoformat()
                self.updated_at = datetime.now().isoformat()
                break
        
        # Update completed status
        self.completed = all(
            item.status in [ChecklistItemStatus.CHECKED, ChecklistItemStatus.SKIPPED]
            for item in self.items
        )
    
    def mark_in_progress(self, item_id: int) -> None:
        """Mark an item as in progress."""
        for item in self.items:
            if item.id == item_id:
                item.status = ChecklistItemStatus.IN_PROGRESS
                item.started_at = datetime.now().isoformat()
                self.updated_at = datetime.now().isoformat()
                break
    
    def reset_item(self, item_id: int) -> None:
        """Reset an item to unchecked."""
        for item in self.items:
            if item.id == item_id:
                item.status = ChecklistItemStatus.UNCHECKED
                item.started_at = None
                item.completed_at = None
                item.error = None
                self.updated_at = datetime.now().isoformat()
                self.completed = False
                break


class ChecklistParser:
    """Parser for markdown checklists."""
    
    CHECKBOX_PATTERN = re.compile(r'^(\s*[-*+]\s+\[( |x|X)\]\s+)(.+)$', re.MULTILINE)
    CHECKBOX_SIMPLE_PATTERN = re.compile(r'^(\s*[-*+]\s+)(\[( |x|X)\]\s+)?(.+)$', re.MULTILINE)
    
    @classmethod
    def parse_markdown(cls, markdown: str) -> Checklist:
        """
        Parse markdown text and extract checklist items.
        
        Supports:
        - [ ] Unchecked item
        - [x] Checked item
        - [X] Checked item
        - Plain list items (treat as unchecked)
        """
        items = []
        item_id = 0
        
        lines = markdown.split('\n')
        for line in lines:
            # Try checkbox pattern first
            checkbox_match = cls.CHECKBOX_PATTERN.match(line)
            if checkbox_match:
                checkbox_char = checkbox_match.group(2)
                text = checkbox_match.group(3).strip()
                
                status = ChecklistItemStatus.CHECKED if checkbox_char in ('x', 'X') else ChecklistItemStatus.UNCHECKED
                items.append(ChecklistItem(id=item_id, text=text, status=status))
                item_id += 1
                continue
            
            # Try simple list pattern (without checkbox)
            simple_match = cls.CHECKBOX_SIMPLE_PATTERN.match(line)
            if simple_match:
                text = simple_match.group(4).strip() if simple_match.group(4) else simple_match.group(1).strip()
                if text and not text.startswith('-') and not text.startswith('*') and not text.startswith('+'):
                    items.append(ChecklistItem(id=item_id, text=text, status=ChecklistItemStatus.UNCHECKED))
                    item_id += 1
        
        return Checklist(items=items)
    
    @classmethod
    def extract_checklist_from_text(cls, text: str) -> Optional[Checklist]:
        """
        Extract checklist from any text containing markdown.
        Returns None if no checklist found.
        """
        checklist = cls.parse_markdown(text)
        if checklist.items:
            return checklist
        return None
    
    @classmethod
    def markdown_with_progress(cls, checklist: Checklist) -> str:
        """Generate markdown representation with current progress."""
        lines = []
        lines.append(f"# Checklist (Progress: {checklist.progress:.1f}%)")
        lines.append("")
        
        for item in checklist.items:
            checkbox = "[x]" if item.status == ChecklistItemStatus.CHECKED else "[ ]"
            status_indicator = ""
            if item.status == ChecklistItemStatus.IN_PROGRESS:
                status_indicator = " ⏳"
            elif item.status == ChecklistItemStatus.FAILED:
                status_indicator = " ❌"
            elif item.status == ChecklistItemStatus.SKIPPED:
                status_indicator = " ⏭️"
            
            lines.append(f"- {checkbox} {item.text}{status_indicator}")
            
            if item.error:
                lines.append(f"  > Error: {item.error}")
            elif item.completed_at:
                lines.append(f"  > Completed: {item.completed_at}")
        
        lines.append("")
        lines.append(f"**{len(checklist.checked_items)}/{len(checklist.items)} items completed**")
        return "\n".join(lines)


class ChecklistManager:
    """Manages checklist execution and persistence."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.persistence = ensure_skillweave_folder(project_root)
        self.config = self.persistence.load_config()
        
    def is_enabled(self) -> bool:
        """Check if checklist execution is enabled."""
        return is_feature_enabled("checklist_execution", self.persistence.project_root)
    
    def get_checklist_path(self, checklist_hash: str) -> Path:
        """Get path for checklist state file."""
        return self.persistence.skillweave_dir / "tracking-log" / f"checklist-{checklist_hash}.json"
    
    def save_checklist(self, checklist: Checklist) -> Path:
        """Save checklist state to file."""
        if not self.is_enabled():
            raise ValueError("Checklist execution is disabled")
        
        checklist_hash = checklist.get_hash()
        path = self.get_checklist_path(checklist_hash)
        
        data = checklist.to_dict()
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        return path
    
    def load_checklist(self, checklist_hash: str) -> Optional[Checklist]:
        """Load checklist state from file."""
        if not self.is_enabled():
            return None
        
        path = self.get_checklist_path(checklist_hash)
        if not path.exists():
            return None
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        return Checklist.from_dict(data)
    
    def find_checklist_in_text(self, text: str) -> Optional[Checklist]:
        """
        Find and load existing checklist from text, or create new one.
        
        Returns:
            - Existing checklist if found and feature enabled
            - New checklist if found and no existing state
            - None if no checklist found or feature disabled
        """
        if not self.is_enabled():
            return None
        
        checklist = ChecklistParser.extract_checklist_from_text(text)
        if not checklist:
            return None
        
        checklist_hash = checklist.get_hash()
        existing = self.load_checklist(checklist_hash)
        
        if existing:
            # Update new checklist items with existing status
            # This handles cases where checklist might have been modified
            for new_item in checklist.items:
                for existing_item in existing.items:
                    if new_item.text == existing_item.text:
                        new_item.status = existing_item.status
                        new_item.started_at = existing_item.started_at
                        new_item.completed_at = existing_item.completed_at
                        new_item.error = existing_item.error
                        break
            return existing
        else:
            return checklist
    
    def should_continue(self, checklist: Checklist) -> bool:
        """
        Determine if we should continue checklist execution.
        
        Based on:
        - Whether there are unchecked items
        - Mode-specific settings (max iterations, auto_continue)
        """
        if checklist.completed:
            return False
        
        if not checklist.unchecked_items:
            return False
        
        # Check mode-specific settings
        mode = self.config.mode.value
        if mode == "conservative":
            # Conservative mode might require manual confirmation
            # This would be handled by the skill, not here
            return True
        elif mode == "unicorn":
            # Unicorn mode continues aggressively
            return True
        else:  # medium
            return True
    
    def execute_checklist_loop(self, checklist: Checklist, executor_func) -> Tuple[Checklist, bool]:
        """
        Execute checklist items in a loop.
        
        Args:
            checklist: Checklist to execute
            executor_func: Function that takes (item_text, item_id) and returns success
        
        Returns:
            Tuple of (updated_checklist, completed)
        """
        if not self.is_enabled():
            return checklist, False
        
        iteration = 0
        max_iterations = 50  # Safety limit
        
        while self.should_continue(checklist) and iteration < max_iterations:
            iteration += 1
            
            for item in checklist.unchecked_items:
                # Mark as in progress
                checklist.mark_in_progress(item.id)
                self.save_checklist(checklist)
                
                try:
                    # Execute the item
                    success = executor_func(item.text, item.id)
                    
                    if success:
                        checklist.mark_checked(item.id)
                    else:
                        checklist.mark_checked(item.id, error="Execution failed")
                except Exception as e:
                    checklist.mark_checked(item.id, error=str(e))
                
                # Save after each item
                self.save_checklist(checklist)
        
        return checklist, checklist.completed