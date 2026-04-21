"""
Unit tests for checklist module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import shutil
from pathlib import Path

from skillweave.checklist import (
    Checklist,
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistParser,
    ChecklistManager,
)
from skillweave.persistence import SkillWeavePersistence


def test_checklist_item():
    """Test ChecklistItem class."""
    item = ChecklistItem(id=0, text="Test item")
    assert item.id == 0
    assert item.text == "Test item"
    assert item.status == ChecklistItemStatus.UNCHECKED
    assert item.started_at is None
    assert item.completed_at is None
    assert item.error is None
    
    # Test to_dict and from_dict
    item_dict = item.to_dict()
    assert item_dict["id"] == 0
    assert item_dict["text"] == "Test item"
    assert item_dict["status"] == "unchecked"
    
    restored = ChecklistItem.from_dict(item_dict)
    assert restored.id == item.id
    assert restored.text == item.text
    assert restored.status == item.status


def test_checklist():
    """Test Checklist class."""
    items = [
        ChecklistItem(id=0, text="Item 1"),
        ChecklistItem(id=1, text="Item 2"),
        ChecklistItem(id=2, text="Item 3"),
    ]
    checklist = Checklist(items=items)
    
    assert len(checklist.items) == 3
    assert checklist.completed is False
    
    # Test unchecked_items
    assert len(checklist.unchecked_items) == 3
    
    # Test mark_checked
    checklist.mark_checked(0)
    assert checklist.items[0].status == ChecklistItemStatus.CHECKED
    assert len(checklist.checked_items) == 1
    assert len(checklist.unchecked_items) == 2
    
    # Test mark_in_progress
    checklist.mark_in_progress(1)
    assert checklist.items[1].status == ChecklistItemStatus.IN_PROGRESS
    assert checklist.items[1].started_at is not None
    
    # Test progress calculation
    assert checklist.progress == (1 / 3) * 100
    
    # Test completed status
    checklist.mark_checked(1)
    checklist.mark_checked(2)
    assert checklist.completed is True
    assert checklist.progress == 100.0
    
    # Test hash generation
    hash1 = checklist.get_hash()
    assert len(hash1) == 16  # 16 chars from sha256
    
    # Different checklist should have different hash
    different = Checklist(items=[ChecklistItem(id=0, text="Different")])
    assert different.get_hash() != hash1


def test_checklist_parser():
    """Test ChecklistParser class."""
    parser = ChecklistParser()
    
    # Test parsing markdown with checkboxes
    markdown = """
# My Checklist
- [ ] Item 1
- [x] Item 2 (completed)
- [ ] Item 3
- [X] Item 4 (also completed)
"""
    checklist = parser.parse_markdown(markdown)
    
    assert len(checklist.items) == 4
    assert checklist.items[0].text == "Item 1"
    assert checklist.items[0].status == ChecklistItemStatus.UNCHECKED
    assert checklist.items[1].text == "Item 2 (completed)"
    assert checklist.items[1].status == ChecklistItemStatus.CHECKED
    assert checklist.items[2].text == "Item 3"
    assert checklist.items[3].status == ChecklistItemStatus.CHECKED  # [X] also checked
    
    # Test parsing plain list items (no checkbox)
    plain_markdown = """
- Item A
- Item B
- Item C
"""
    checklist = parser.parse_markdown(plain_markdown)
    assert len(checklist.items) == 3
    assert checklist.items[0].text == "Item A"
    assert checklist.items[0].status == ChecklistItemStatus.UNCHECKED
    
    # Test mixed content
    mixed = """
# Mixed
- [ ] Checkbox item
- Plain item
- [x] Completed checkbox
"""
    checklist = parser.parse_markdown(mixed)
    assert len(checklist.items) == 3
    assert checklist.items[0].text == "Checkbox item"
    assert checklist.items[0].status == ChecklistItemStatus.UNCHECKED
    assert checklist.items[1].text == "Plain item"
    assert checklist.items[1].status == ChecklistItemStatus.UNCHECKED
    assert checklist.items[2].text == "Completed checkbox"
    assert checklist.items[2].status == ChecklistItemStatus.CHECKED
    
    # Test extract_checklist_from_text
    text_with_checklist = """
Some text before.
- [ ] Task 1
- [ ] Task 2
Some text after.
"""
    checklist = parser.extract_checklist_from_text(text_with_checklist)
    assert checklist is not None
    assert len(checklist.items) == 2
    
    # Test text without checklist
    text_without = "No checklist here."
    checklist = parser.extract_checklist_from_text(text_without)
    assert checklist is None


def test_checklist_manager():
    """Test ChecklistManager class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create persistence first
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Enable checklist feature in config
        config = persistence.load_config()
        config.features["checklist_execution"] = True
        persistence.save_config(config)
        
        manager = ChecklistManager(tmpdir)
        assert manager.is_enabled() is True
        
        # Create a checklist
        checklist = Checklist(items=[
            ChecklistItem(id=0, text="Task 1"),
            ChecklistItem(id=1, text="Task 2"),
        ])
        
        # Save checklist
        path = manager.save_checklist(checklist)
        assert path.exists()
        assert "checklist-" in path.name
        
        # Load checklist
        checklist_hash = checklist.get_hash()
        loaded = manager.load_checklist(checklist_hash)
        assert loaded is not None
        assert len(loaded.items) == 2
        assert loaded.items[0].text == "Task 1"
        
        # Test find_checklist_in_text
        markdown = "- [ ] Task 1\n- [ ] Task 2"
        found = manager.find_checklist_in_text(markdown)
        assert found is not None
        assert len(found.items) == 2
        
        # Should return existing state (which is empty/unchecked)
        assert found.items[0].status == ChecklistItemStatus.UNCHECKED
        
        # Mark one as checked and save
        found.mark_checked(0)
        manager.save_checklist(found)
        
        # Now find again should have checked item
        found2 = manager.find_checklist_in_text(markdown)
        assert found2 is not None
        assert found2.items[0].status == ChecklistItemStatus.CHECKED
        assert found2.items[1].status == ChecklistItemStatus.UNCHECKED


def test_markdown_with_progress():
    """Test markdown generation with progress."""
    items = [
        ChecklistItem(id=0, text="Item 1", status=ChecklistItemStatus.CHECKED),
        ChecklistItem(id=1, text="Item 2", status=ChecklistItemStatus.IN_PROGRESS),
        ChecklistItem(id=2, text="Item 3", status=ChecklistItemStatus.UNCHECKED),
    ]
    checklist = Checklist(items=items)
    
    markdown = ChecklistParser.markdown_with_progress(checklist)
    
    assert "Checklist (Progress:" in markdown
    assert "[x] Item 1" in markdown
    assert "[ ] Item 2" in markdown  # In progress still shows as unchecked in markdown
    assert "[ ] Item 3" in markdown
    assert "⏳" in markdown  # In progress indicator
    assert "1/3 items completed" in markdown