from typing import Any, Dict

class FakeHarness:
    """Hermetic Fake Harness for CI testing."""
    def __init__(self, name: str = "fake-ci-harness"):
        self.name = name
        self.ran_commands = []
        
    def execute(self, command: list[str]) -> Dict[str, Any]:
        self.ran_commands.append(command)
        return {
            "exit_code": 0,
            "stdout": b"fake output",
            "stderr": b""
        }
