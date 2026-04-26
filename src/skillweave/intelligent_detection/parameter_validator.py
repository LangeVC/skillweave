"""
Parameter validator for SkillWeave intelligent detection engine.

Validates parameters against skill requirements, identifies missing required
parameters, and suggests corrections or alternatives.

This is the initial implementation for T-018. Future enhancements may
include type validation, value range checking, and dependency validation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Union, Tuple
from .skill_intent_mapper import Skill


class ValidationSeverity(str, Enum):
    """Severity level for validation findings."""
    ERROR = "error"      # Required parameter missing or invalid
    WARNING = "warning"  # Optional parameter issues or suggestions
    INFO = "info"       # Informational notes


@dataclass
class ValidationFinding:
    """Individual validation finding."""
    parameter: str
    severity: ValidationSeverity
    message: str
    suggestion: Optional[str]
    current_value: Optional[Any]


@dataclass
class ParameterValidationResult:
    """Result of parameter validation."""
    is_valid: bool
    findings: List[ValidationFinding]
    missing_required: List[str]
    suggested_corrections: Dict[str, str]
    completeness_score: float  # 0.0 to 1.0


class ParameterValidator:
    """
    Validates parameters against skill requirements.
    
    Features:
    - Required parameter validation
    - Parameter type and format checking
    - Value suggestion and correction
    - Completeness scoring
    """
    
    # Skill parameter schemas
    # Each entry: parameter_name -> {"required": bool, "type": str, "allowed_values": list, "description": str}
    SKILL_PARAMETER_SCHEMAS: Dict[Skill, Dict[str, Dict[str, Any]]] = {
        Skill.BLUEPRINT: {
            "idea": {
                "required": False,
                "type": "string",
                "description": "Project idea or concept",
                "suggestion_patterns": [
                    r'^[A-Za-z0-9\s\-\.,;:!?]{10,200}$',  # Basic text validation
                ]
            },
            "domain": {
                "required": False,
                "type": "string",
                "allowed_values": ["saas", "mobile", "web", "enterprise", "ecommerce", "iot", "ai", "blockchain"],
                "description": "Domain context",
            },
            "complexity": {
                "required": False,
                "type": "string",
                "allowed_values": ["simple", "medium", "complex"],
                "description": "Complexity level",
            },
            "output_format": {
                "required": False,
                "type": "string",
                "allowed_values": ["json", "markdown", "both"],
                "description": "Output format",
            },
            "risk_mode": {
                "required": False,
                "type": "string",
                "allowed_values": ["conservative", "medium", "unicorn"],
                "description": "Risk mode override",
            },
        },
        Skill.PROMPTCHAIN_GENERATE: {
            "skill": {
                "required": True,
                "type": "string",
                "allowed_values": ["skillweave-blueprint", "skillweave-promptchain-validate", 
                                  "skillweave-promptchain-execute", "skillweave-releasechain"],
                "description": "Target skill for promptchain generation",
            },
            "complexity": {
                "required": False,
                "type": "string",
                "allowed_values": ["simple", "standard", "complex"],
                "description": "Promptchain complexity",
            },
            "output_format": {
                "required": False,
                "type": "string",
                "allowed_values": ["yaml", "json", "markdown"],
                "description": "Output format",
            },
            "risk_mode": {
                "required": False,
                "type": "string",
                "allowed_values": ["conservative", "medium", "unicorn"],
                "description": "Risk mode override",
            },
        },
        Skill.PROMPTCHAIN_VALIDATE: {
            "skill": {
                "required": True,
                "type": "string",
                "description": "Skill name or prompt sequence to validate",
            },
            "risk_mode": {
                "required": False,
                "type": "string",
                "allowed_values": ["conservative", "medium", "unicorn"],
                "description": "Risk mode override",
            },
        },
        Skill.PROMPTCHAIN_EXECUTE: {
            "skill": {
                "required": True,
                "type": "string",
                "description": "Skill name or prompt sequence to execute",
            },
            "risk_mode": {
                "required": False,
                "type": "string",
                "allowed_values": ["conservative", "medium", "unicorn"],
                "description": "Risk mode override",
            },
        },
        Skill.RELEASECHAIN: {
            "skill": {
                "required": True,
                "type": "string",
                "description": "Skill name, PRD, or sequence for releasechain",
            },
            "risk_mode": {
                "required": False,
                "type": "string",
                "allowed_values": ["conservative", "medium", "unicorn"],
                "description": "Risk mode override",
            },
        },
    }
    
    # Parameter normalization rules
    # Maps common variations to standard parameter names
    PARAMETER_ALIASES: Dict[str, str] = {
        "project": "idea",
        "concept": "idea",
        "category": "domain",
        "type": "domain",
        "level": "complexity",
        "difficulty": "complexity",
        "format": "output_format",
        "mode": "risk_mode",
        "target": "skill",
        "sequence": "skill",
    }
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize parameter validator.
        
        Args:
            strict_mode: If True, treat missing required parameters as errors.
                        If False, treat as warnings with suggestions.
        """
        self.strict_mode = strict_mode
    
    def validate(
        self, 
        skill: Skill, 
        parameters: Dict[str, Any],
        normalize: bool = True
    ) -> ParameterValidationResult:
        """
        Validate parameters against skill requirements.
        
        Args:
            skill: Target skill
            parameters: Dictionary of parameters to validate
            normalize: If True, normalize parameter names using aliases
            
        Returns:
            ParameterValidationResult with validation findings
        """
        # Step 1: Normalize parameter names
        normalized_params = self._normalize_parameters(parameters) if normalize else parameters.copy()
        
        # Step 2: Get skill schema
        skill_schema = self.SKILL_PARAMETER_SCHEMAS.get(skill, {})
        
        # Step 3: Validate each parameter in schema
        findings: List[ValidationFinding] = []
        missing_required: List[str] = []
        
        for param_name, param_schema in skill_schema.items():
            param_value = normalized_params.get(param_name)
            
            # Check if parameter is present
            if param_value is None:
                if param_schema.get("required", False):
                    missing_required.append(param_name)
                    findings.append(self._create_missing_finding(param_name, param_schema))
                continue
            
            # Validate parameter value
            param_findings = self._validate_parameter_value(param_name, param_value, param_schema)
            findings.extend(param_findings)
        
        # Step 4: Check for unknown parameters
        unknown_findings = self._check_unknown_parameters(normalized_params, skill_schema)
        findings.extend(unknown_findings)
        
        # Step 5: Generate suggested corrections
        suggested_corrections = self._generate_corrections(findings, normalized_params, skill_schema)
        
        # Step 6: Calculate completeness score
        completeness_score = self._calculate_completeness_score(
            skill_schema, normalized_params, missing_required
        )
        
        # Step 7: Determine overall validity
        is_valid = self._determine_validity(missing_required, findings)
        
        return ParameterValidationResult(
            is_valid=is_valid,
            findings=findings,
            missing_required=missing_required,
            suggested_corrections=suggested_corrections,
            completeness_score=completeness_score
        )
    
    def validate_single_parameter(
        self,
        skill: Skill,
        parameter_name: str,
        value: Any,
        param_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Validate a single parameter value.
        
        Args:
            skill: Target skill
            parameter_name: Name of parameter to validate
            value: Parameter value
            param_info: Optional pre-fetched parameter schema (saves lookup)
            
        Returns:
            Tuple of (is_valid, validation_message)
        """
        # Get parameter info if not provided
        if param_info is None:
            param_info = self.get_parameter_info(skill, parameter_name)
        
        # If parameter not in schema, assume valid (unknown parameter)
        if param_info is None:
            return True, "Parameter not in schema (assumed valid)"
        
        # Validate using internal method
        findings = self._validate_parameter_value(parameter_name, value, param_info)
        
        # Check if any findings are errors/warnings
        # For simplicity, treat warnings as valid but provide message
        error_findings = [f for f in findings if f.severity == ValidationSeverity.ERROR]
        warning_findings = [f for f in findings if f.severity == ValidationSeverity.WARNING]
        
        if error_findings:
            # Combine error messages
            messages = [f.message for f in error_findings]
            return False, "; ".join(messages)
        elif warning_findings:
            messages = [f.message for f in warning_findings]
            return True, "; ".join(messages)
        else:
            return True, "Valid"
    
    def _normalize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameter names using aliases."""
        normalized = {}
        
        for param_name, param_value in parameters.items():
            # Convert to lowercase for matching
            param_lower = param_name.lower()
            
            # Check for alias
            normalized_name = self.PARAMETER_ALIASES.get(param_lower, param_name)
            
            # Use the first occurrence if multiple aliases map to same name
            if normalized_name not in normalized:
                normalized[normalized_name] = param_value
            else:
                # Duplicate parameter - keep first value, create warning
                pass
        
        return normalized
    
    def _create_missing_finding(
        self, 
        param_name: str, 
        param_schema: Dict[str, Any]
    ) -> ValidationFinding:
        """Create validation finding for missing required parameter."""
        severity = ValidationSeverity.ERROR if self.strict_mode else ValidationSeverity.WARNING
        
        description = param_schema.get("description", "")
        allowed_values = param_schema.get("allowed_values")
        
        suggestion = f"Provide {param_name}"
        if allowed_values:
            suggestion += f" (allowed: {', '.join(allowed_values)})"
        
        return ValidationFinding(
            parameter=param_name,
            severity=severity,
            message=f"Missing required parameter: {param_name}",
            suggestion=suggestion,
            current_value=None
        )
    
    def _validate_parameter_value(
        self, 
        param_name: str, 
        param_value: Any,
        param_schema: Dict[str, Any]
    ) -> List[ValidationFinding]:
        """Validate a parameter value against schema."""
        findings = []
        
        # Type validation
        expected_type = param_schema.get("type")
        if expected_type:
            type_valid = self._check_type(param_value, expected_type)
            if not type_valid:
                findings.append(ValidationFinding(
                    parameter=param_name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Parameter {param_name} has unexpected type. Expected {expected_type}.",
                    suggestion=f"Convert to {expected_type}",
                    current_value=param_value
                ))
        
        # Allowed values validation
        allowed_values = param_schema.get("allowed_values")
        if allowed_values and param_value not in allowed_values:
            # Try case-insensitive match
            if isinstance(param_value, str):
                param_lower = param_value.lower()
                allowed_lower = [v.lower() for v in allowed_values]
                if param_lower in allowed_lower:
                    # Case mismatch - suggest correct case
                    idx = allowed_lower.index(param_lower)
                    corrected = allowed_values[idx]
                    findings.append(ValidationFinding(
                        parameter=param_name,
                        severity=ValidationSeverity.INFO,
                        message=f"Parameter {param_name} value has case mismatch",
                        suggestion=f"Use '{corrected}' instead of '{param_value}'",
                        current_value=param_value
                    ))
                else:
                    # Value not in allowed list
                    findings.append(ValidationFinding(
                        parameter=param_name,
                        severity=ValidationSeverity.WARNING,
                        message=f"Parameter {param_name} value '{param_value}' not in allowed values",
                        suggestion=f"Use one of: {', '.join(allowed_values)}",
                        current_value=param_value
                    ))
        
        # Pattern validation (for strings)
        suggestion_patterns = param_schema.get("suggestion_patterns", [])
        if suggestion_patterns and isinstance(param_value, str):
            for pattern in suggestion_patterns:
                import re
                if not re.match(pattern, param_value):
                    findings.append(ValidationFinding(
                        parameter=param_name,
                        severity=ValidationSeverity.INFO,
                        message=f"Parameter {param_name} value doesn't match expected pattern",
                        suggestion="Consider providing more detailed information",
                        current_value=param_value
                    ))
                    break
        
        return findings
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        python_type = type_map.get(expected_type)
        if not python_type:
            return True  # Unknown type, skip validation
        
        if isinstance(python_type, tuple):
            return isinstance(value, python_type)
        else:
            return isinstance(value, python_type)
    
    def _check_unknown_parameters(
        self, 
        parameters: Dict[str, Any], 
        skill_schema: Dict[str, Dict[str, Any]]
    ) -> List[ValidationFinding]:
        """Check for parameters not defined in schema."""
        findings = []
        schema_params = set(skill_schema.keys())
        
        for param_name in parameters.keys():
            if param_name not in schema_params:
                # Check if it's a known alias
                is_alias = param_name in self.PARAMETER_ALIASES.values() or param_name in self.PARAMETER_ALIASES.keys()
                
                if is_alias:
                    # Already normalized, but not in schema
                    continue
                
                findings.append(ValidationFinding(
                    parameter=param_name,
                    severity=ValidationSeverity.INFO,
                    message=f"Unknown parameter: {param_name}",
                    suggestion="Consider removing or checking parameter name",
                    current_value=parameters[param_name]
                ))
        
        return findings
    
    def _generate_corrections(
        self,
        findings: List[ValidationFinding],
        parameters: Dict[str, Any],
        skill_schema: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """Generate suggested corrections for validation findings."""
        corrections = {}
        
        for finding in findings:
            if finding.suggestion and (
                finding.severity == ValidationSeverity.ERROR or
                (finding.severity == ValidationSeverity.WARNING and finding.current_value is None)
            ):
                param_name = finding.parameter
                
                # For missing parameters, suggest a placeholder
                if finding.current_value is None:
                    # Check if parameter has allowed values
                    param_schema = skill_schema.get(param_name, {})
                    allowed_values = param_schema.get("allowed_values")
                    
                    if allowed_values:
                        # Suggest first allowed value as placeholder
                        corrections[param_name] = allowed_values[0]
                    else:
                        # Suggest generic placeholder
                        corrections[param_name] = f"[provide {param_name}]"
                
                # For value corrections, suggest alternative
                elif finding.current_value is not None and finding.suggestion:
                    # Extract suggested value from suggestion text if possible
                    suggestion = finding.suggestion
                    if "Use '" in suggestion and "' instead" in suggestion:
                        start = suggestion.find("Use '") + 5
                        end = suggestion.find("' instead")
                        if start > 4 and end > start:
                            corrections[param_name] = suggestion[start:end]
        
        return corrections
    
    def _calculate_completeness_score(
        self,
        skill_schema: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
        missing_required: List[str]
    ) -> float:
        """Calculate completeness score (0.0 to 1.0)."""
        if not skill_schema:
            return 1.0  # No schema, assume complete
        
        total_params = len(skill_schema)
        required_params = sum(1 for schema in skill_schema.values() if schema.get("required", False))
        
        if total_params == 0:
            return 1.0
        
        # Base score: proportion of provided parameters
        provided_count = sum(1 for param_name in skill_schema.keys() if param_name in parameters)
        base_score = provided_count / total_params
        
        # Penalty for missing required parameters
        required_penalty = len(missing_required) * (1.0 / max(required_params, 1))
        
        # Final score
        final_score = base_score * (1.0 - required_penalty * 0.5)
        
        return max(min(final_score, 1.0), 0.0)
    
    def _determine_validity(
        self, 
        missing_required: List[str], 
        findings: List[ValidationFinding]
    ) -> bool:
        """Determine if parameters are valid based on findings."""
        if missing_required:
            return False
        
        has_errors = any(f.severity == ValidationSeverity.ERROR for f in findings)
        
        return not has_errors
    
    def suggest_parameters(
        self, 
        skill: Skill, 
        partial_parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Suggest missing parameters based on partial input.
        
        Args:
            skill: Target skill
            partial_parameters: Already provided parameters
            
        Returns:
            Dictionary of suggested parameter completions
        """
        suggestions = {}
        skill_schema = self.SKILL_PARAMETER_SCHEMAS.get(skill, {})
        
        for param_name, param_schema in skill_schema.items():
            if param_name not in partial_parameters:
                # Suggest a value based on schema
                allowed_values = param_schema.get("allowed_values")
                if allowed_values:
                    suggestions[param_name] = allowed_values[0]
                else:
                    # Generic suggestion based on parameter type
                    param_type = param_schema.get("type", "string")
                    if param_type == "string":
                        suggestions[param_name] = f"[{param_name}]"
                    elif param_type == "integer":
                        suggestions[param_name] = 1
                    elif param_type == "boolean":
                        suggestions[param_name] = True
                    elif param_type == "array":
                        suggestions[param_name] = []
                    elif param_type == "object":
                        suggestions[param_name] = {}
        
        return suggestions
    
    def get_parameter_info(
        self,
        skill: Skill,
        parameter_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get schema information for a specific parameter.
        
        Args:
            skill: Target skill
            parameter_name: Name of parameter
            
        Returns:
            Parameter schema dictionary or None if not found
        """
        skill_schema = self.SKILL_PARAMETER_SCHEMAS.get(skill, {})
        return skill_schema.get(parameter_name)
    
    def migrate_parameters(
        self,
        source_skill: Skill,
        target_skill: Skill,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Migrate parameters from source skill to target skill.
        
        Parameters are mapped based on:
        1. Exact parameter name match
        2. Alias mapping (normalization)
        3. Semantic similarity (future enhancement)
        
        Args:
            source_skill: Source skill
            target_skill: Target skill
            parameters: Parameters from source skill
            
        Returns:
            Migrated parameters for target skill
        """
        if source_skill == target_skill:
            return parameters.copy()
        
        target_schema = self.SKILL_PARAMETER_SCHEMAS.get(target_skill, {})
        migrated = {}
        
        for param_name, param_value in parameters.items():
            # Step 1: Normalize parameter name using aliases
            normalized_name = self.PARAMETER_ALIASES.get(param_name.lower(), param_name)
            
            # Step 2: Check if normalized name exists in target schema
            if normalized_name in target_schema:
                migrated[normalized_name] = param_value
                continue
            
            # Step 3: Check if original name exists in target schema
            if param_name in target_schema:
                migrated[param_name] = param_value
                continue
            
            # Step 4: Check if parameter name matches any target parameter by substring
            # (simple heuristic for semantic similarity)
            for target_param in target_schema.keys():
                if (param_name.lower() in target_param.lower() or 
                    target_param.lower() in param_name.lower()):
                    migrated[target_param] = param_value
                    break
        
        # Step 5: Validate migrated parameters
        validation = self.validate(target_skill, migrated, normalize=False)
        
        # Remove parameters that cause validation errors
        if not validation.is_valid:
            for finding in validation.findings:
                if finding.severity == ValidationSeverity.ERROR and finding.parameter in migrated:
                    del migrated[finding.parameter]
        
        return migrated
    
    def batch_validate(
        self, 
        skills: List[Skill], 
        parameters_list: List[Dict[str, Any]]
    ) -> List[ParameterValidationResult]:
        """Validate multiple parameter sets."""
        results = []
        for skill, params in zip(skills, parameters_list):
            results.append(self.validate(skill, params))
        return results


# Convenience function
def validate_parameters(
    skill: Skill, 
    parameters: Dict[str, Any], 
    strict_mode: bool = False
) -> ParameterValidationResult:
    """Convenience function for quick parameter validation."""
    validator = ParameterValidator(strict_mode=strict_mode)
    return validator.validate(skill, parameters)