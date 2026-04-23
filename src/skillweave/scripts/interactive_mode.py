#!/usr/bin/env python3
"""
Interactive risk mode selection with project analysis and persistence options.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skillweave.interactive_mode_selector import interactive_mode_selection

def main():
    """Run interactive mode selection and persist if requested."""
    try:
        selected_mode, persistence = interactive_mode_selection()
        print(f"Selected risk mode: {selected_mode}")
        print(f"Persistence: {persistence}")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())