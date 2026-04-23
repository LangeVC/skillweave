"""
Learning system for SkillWeave intelligent detection engine.

Tracks user feedback and adapts detection thresholds and recommendations
based on user preferences and historical patterns.

This is the initial implementation for T-023. Future enhancements may
include machine learning models and community pattern sharing.
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from .skill_intent_mapper import Skill

try:
    from ..persistence import SkillWeavePersistence, get_persistence
    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False


class FeedbackEventType(str, Enum):
    """Types of feedback events."""
    RECOMMENDATION_SHOWN = "recommendation_shown"
    RECOMMENDATION_ACCEPTED = "recommendation_accepted"
    RECOMMENDATION_REJECTED = "recommendation_rejected"
    SKILL_SWITCHED = "skill_switched"
    PARAMETERS_PROVIDED = "parameters_provided"
    PARAMETERS_CORRECTED = "parameters_corrected"
    MANUAL_OVERRIDE = "manual_override"


@dataclass
class FeedbackEvent:
    """Individual feedback event."""
    event_type: FeedbackEventType
    timestamp: str
    session_id: str
    prompt_hash: str  # Hash of original prompt for anonymity
    detected_skill: Optional[Skill] = None
    current_skill: Optional[Skill] = None
    confidence_score: float = 0.0
    intervention_level: str = "none"
    user_action: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FeedbackTracker:
    """
    Tracks user feedback events for learning and adaptation.
    
    Features:
    - Event logging with anonymized prompts
    - Session-based tracking
    - Configurable storage (local files)
    - Privacy-conscious design (hashed prompts)
    """
    
    def __init__(self, project_root: Optional[str] = None, session_id: Optional[str] = None):
        """
        Initialize feedback tracker.
        
        Args:
            project_root: Project root directory
            session_id: Optional session ID (auto-generated if None)
        """
        self.project_root = project_root
        self.session_id = session_id or self._generate_session_id()
        self.persistence = None
        
        if PERSISTENCE_AVAILABLE:
            self.persistence = get_persistence(project_root)
            # Ensure feedback directory exists
            self._ensure_feedback_dir()
    
    def _ensure_feedback_dir(self):
        """Ensure feedback directory exists."""
        if not self.persistence:
            return
        feedback_dir = self.persistence.skillweave_dir / "feedback"
        feedback_dir.mkdir(exist_ok=True)
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = hashlib.md5(timestamp.encode()).hexdigest()[:8]
        return f"session_{timestamp}_{random_suffix}"
    
    def _hash_prompt(self, prompt: str) -> str:
        """Create anonymous hash of prompt for tracking."""
        # Use SHA-256 for one-way hashing
        return hashlib.sha256(prompt.encode()).hexdigest()
    
    def log_event(
        self,
        event_type: FeedbackEventType,
        prompt: str,
        detected_skill: Optional[Skill] = None,
        current_skill: Optional[Skill] = None,
        confidence_score: float = 0.0,
        intervention_level: str = "none",
        user_action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> FeedbackEvent:
        """
        Log a feedback event.
        
        Returns:
            The created FeedbackEvent
        """
        event = FeedbackEvent(
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            session_id=self.session_id,
            prompt_hash=self._hash_prompt(prompt),
            detected_skill=detected_skill,
            current_skill=current_skill,
            confidence_score=confidence_score,
            intervention_level=intervention_level,
            user_action=user_action,
            metadata=metadata or {}
        )
        
        self._save_event(event)
        return event
    
    def _save_event(self, event: FeedbackEvent):
        """Save event to storage."""
        if not self.persistence:
            return  # No persistence, skip saving
        
        # Save to feedback directory
        feedback_dir = self.persistence.skillweave_dir / "feedback"
        feedback_dir.mkdir(exist_ok=True)
        
        # Create filename with timestamp and event type
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}_{event.event_type}_{event.session_id[:8]}.json"
        filepath = feedback_dir / filename
        
        # Convert to dict
        event_dict = asdict(event)
        # Convert enums to strings
        event_dict["event_type"] = event.event_type.value
        if event.detected_skill:
            event_dict["detected_skill"] = event.detected_skill.value
        if event.current_skill:
            event_dict["current_skill"] = event.current_skill.value
        
        with open(filepath, 'w') as f:
            json.dump(event_dict, f, indent=2, default=str)
    
    def get_session_events(self, session_id: Optional[str] = None) -> List[FeedbackEvent]:
        """Get all events for a session."""
        if not self.persistence:
            return []
        
        session_id = session_id or self.session_id
        feedback_dir = self.persistence.skillweave_dir / "feedback"
        
        if not feedback_dir.exists():
            return []
        
        events = []
        for filepath in feedback_dir.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                # Filter by session_id
                if data.get("session_id") == session_id:
                    # Convert back to FeedbackEvent
                    event = FeedbackEvent(
                        event_type=FeedbackEventType(data["event_type"]),
                        timestamp=data["timestamp"],
                        session_id=data["session_id"],
                        prompt_hash=data["prompt_hash"],
                        detected_skill=Skill(data["detected_skill"]) if data.get("detected_skill") else None,
                        current_skill=Skill(data["current_skill"]) if data.get("current_skill") else None,
                        confidence_score=data.get("confidence_score", 0.0),
                        intervention_level=data.get("intervention_level", "none"),
                        user_action=data.get("user_action"),
                        metadata=data.get("metadata", {})
                    )
                    events.append(event)
            except:
                continue
        
        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)
        return events
    
    def get_acceptance_rate(self, session_id: Optional[str] = None) -> float:
        """
        Calculate recommendation acceptance rate for session.
        
        Returns:
            Acceptance rate as float between 0.0 and 1.0
        """
        events = self.get_session_events(session_id)
        if not events:
            return 0.5  # Default neutral rate
        
        shown_events = [e for e in events if e.event_type == FeedbackEventType.RECOMMENDATION_SHOWN]
        accepted_events = [e for e in events if e.event_type == FeedbackEventType.RECOMMENDATION_ACCEPTED]
        
        if not shown_events:
            return 0.5
        
        return len(accepted_events) / len(shown_events)


class LearningSystem:
    """
    Learns from user feedback and adjusts detection thresholds.
    
    Features:
    - Adjusts sensitivity based on acceptance rate
    - Learns parameter patterns per skill
    - Updates user preferences
    - Maintains privacy by only storing aggregated patterns
    """
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
        self.feedback_tracker = FeedbackTracker(project_root)
        
        # Load existing patterns if available
        self.patterns = self._load_patterns()
        self.user_preferences = self._load_user_preferences()
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load learned patterns from storage."""
        if not PERSISTENCE_AVAILABLE:
            return {}
        
        try:
            persistence = get_persistence(self.project_root)
            config = persistence.load_config()
            user_prefs = config.intelligent_detection.get("user_preferences", {})
            if isinstance(user_prefs, dict):
                return user_prefs.get("skill_patterns", {})
        except:
            pass
        return {}
    
    def _load_user_preferences(self) -> Dict[str, Any]:
        """Load user preferences from config."""
        if not PERSISTENCE_AVAILABLE:
            return {}
        
        try:
            persistence = get_persistence(self.project_root)
            config = persistence.load_config()
            # Get nested user_preferences dict
            user_prefs = config.intelligent_detection.get("user_preferences", {})
            # Ensure it's a dict
            if not isinstance(user_prefs, dict):
                user_prefs = {}
            # Copy top-level sensitivity and threshold into user_prefs for backward compatibility
            if "sensitivity" in config.intelligent_detection:
                user_prefs["sensitivity"] = config.intelligent_detection["sensitivity"]
            if "auto_switch_threshold" in config.intelligent_detection:
                user_prefs["auto_switch_threshold"] = config.intelligent_detection["auto_switch_threshold"]
            if "learn_from_feedback" in config.intelligent_detection:
                user_prefs["learn_from_feedback"] = config.intelligent_detection["learn_from_feedback"]
            return user_prefs
        except:
            return {}
    
    def _save_user_preferences(self, preferences: Dict[str, Any]):
        """Save user preferences to config."""
        if not PERSISTENCE_AVAILABLE:
            return
        
        try:
            persistence = get_persistence(self.project_root)
            config = persistence.load_config()
            # Ensure user_preferences dict exists
            if "user_preferences" not in config.intelligent_detection:
                config.intelligent_detection["user_preferences"] = {}
            elif not isinstance(config.intelligent_detection["user_preferences"], dict):
                config.intelligent_detection["user_preferences"] = {}
            
            # Update nested user_preferences dict
            config.intelligent_detection["user_preferences"].update(preferences)
            
            # Also update top-level keys for backward compatibility
            # (only keys that are traditionally top-level)
            top_level_keys = ["sensitivity", "auto_switch_threshold", "learn_from_feedback"]
            for key in top_level_keys:
                if key in preferences:
                    config.intelligent_detection[key] = preferences[key]
            
            persistence.save_config(config)
        except:
            pass
    
    def _save_patterns(self):
        """Save learned patterns to config."""
        if not PERSISTENCE_AVAILABLE:
            return
        
        try:
            persistence = get_persistence(self.project_root)
            config = persistence.load_config()
            # Ensure user_preferences dict exists
            if "user_preferences" not in config.intelligent_detection:
                config.intelligent_detection["user_preferences"] = {}
            elif not isinstance(config.intelligent_detection["user_preferences"], dict):
                config.intelligent_detection["user_preferences"] = {}
            
            # Update skill_patterns
            config.intelligent_detection["user_preferences"]["skill_patterns"] = self.patterns
            persistence.save_config(config)
        except:
            pass
    
    def record_feedback(
        self,
        event_type: FeedbackEventType,
        prompt: str,
        detected_skill: Optional[Skill] = None,
        current_skill: Optional[Skill] = None,
        confidence_score: float = 0.0,
        intervention_level: str = "none",
        user_action: Optional[str] = None
    ):
        """Record feedback and update learning."""
        # Log the event
        event = self.feedback_tracker.log_event(
            event_type, prompt, detected_skill, current_skill,
            confidence_score, intervention_level, user_action
        )
        
        # Update learning based on event
        self._update_learning(event)
        
        # Update user preferences based on behavior
        self._update_preferences(event)
    
    def _update_learning(self, event: FeedbackEvent):
        """Update learned patterns based on feedback event."""
        # Simple learning: track skill usage patterns
        if event.detected_skill:
            skill_key = event.detected_skill.value
            if skill_key not in self.patterns:
                self.patterns[skill_key] = {
                    "count": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "avg_confidence": 0.0,
                }
            
            pattern = self.patterns[skill_key]
            pattern["count"] += 1
            
            if event.event_type == FeedbackEventType.RECOMMENDATION_ACCEPTED:
                pattern["accepted"] += 1
            elif event.event_type == FeedbackEventType.RECOMMENDATION_REJECTED:
                pattern["rejected"] += 1
            
            # Update average confidence
            current_avg = pattern["avg_confidence"]
            pattern["avg_confidence"] = (
                (current_avg * (pattern["count"] - 1) + event.confidence_score) 
                / pattern["count"]
            )
            
            # Save updated patterns
            self._save_patterns()
    
    def _update_preferences(self, event: FeedbackEvent):
        """Update user preferences based on feedback."""
        # Check if learning from feedback is enabled
        if not self.user_preferences.get("learn_from_feedback", True):
            return
            
        # Calculate acceptance rate
        acceptance_rate = self.feedback_tracker.get_acceptance_rate(event.session_id)
        
        # Adjust sensitivity based on acceptance rate
        # Low acceptance -> user prefers less intervention -> lower sensitivity
        # High acceptance -> user trusts system -> higher sensitivity
        current_sensitivity = self.user_preferences.get("sensitivity", "medium")
        current_threshold = self.user_preferences.get("auto_switch_threshold", 70)
        
        # Determine new sensitivity
        if acceptance_rate < 0.3:  # Low acceptance
            new_sensitivity = "conservative"
        elif acceptance_rate > 0.7:  # High acceptance
            new_sensitivity = "aggressive"
        else:  # Medium acceptance
            new_sensitivity = "medium"
        
        # Determine new threshold (adjusted based on acceptance rate)
        # Low acceptance -> be more conservative (higher threshold)
        # High acceptance -> be more aggressive (lower threshold)
        if acceptance_rate < 0.3:
            new_threshold = min(current_threshold + 15, 95)
        elif acceptance_rate > 0.7:
            new_threshold = max(current_threshold - 15, 5)
        else:
            new_threshold = current_threshold
        
        # Check if changes are significant enough to save
        preferences_changed = False
        
        if new_sensitivity != current_sensitivity:
            self.user_preferences["sensitivity"] = new_sensitivity
            preferences_changed = True
        
        # Only update threshold if change is at least 5 points (to avoid noise)
        if abs(new_threshold - current_threshold) >= 5:
            self.user_preferences["auto_switch_threshold"] = new_threshold
            preferences_changed = True
        
        # Save if changed
        if preferences_changed:
            self._save_user_preferences(self.user_preferences)
    
    def get_adjusted_sensitivity(self) -> str:
        """Get sensitivity adjusted based on user behavior."""
        return self.user_preferences.get("sensitivity", "medium")
    
    def get_adjusted_threshold(self) -> float:
        """Get auto-switch threshold adjusted based on user behavior."""
        # Return saved threshold (already adjusted by learning system)
        return self.user_preferences.get("auto_switch_threshold", 70)
    
    def suggest_parameters(self, skill: Skill, partial_params: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest parameters based on learned patterns."""
        # TODO: Implement parameter suggestion based on historical patterns
        return {}
    
    def get_skill_confidence_adjustment(self, skill: Skill) -> float:
        """Get confidence adjustment for a skill based on historical acceptance."""
        skill_key = skill.value
        if skill_key in self.patterns:
            pattern = self.patterns[skill_key]
            if pattern["count"] > 0:
                acceptance_rate = pattern["accepted"] / pattern["count"]
                # Boost confidence for skills with high acceptance
                if acceptance_rate > 0.8:
                    return 1.2  # 20% boost
                elif acceptance_rate < 0.2:
                    return 0.8  # 20% reduction
        return 1.0  # No adjustment