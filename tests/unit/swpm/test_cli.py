#!/usr/bin/env python3
"""
Unit tests for SWPM CLI.
"""

import sys
import subprocess
import pytest

def test_cli_help():
    """Test that swpm --help runs without error."""
    result = subprocess.run(
        [sys.executable, "-m", "swpm.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "SkillWeave Package Manager" in result.stdout

def test_cli_version():
    """Test that swpm --version shows version."""
    result = subprocess.run(
        [sys.executable, "-m", "swpm.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "swpm 1.0.0" in result.stdout

def test_cli_no_args_shows_help():
    """Test that swpm with no arguments shows help."""
    result = subprocess.run(
        [sys.executable, "-m", "swpm.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout