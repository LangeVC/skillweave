class StoreError(Exception):
    pass


class InvalidTransitionError(StoreError):
    def __init__(self, current_state, target_state, run_id, extra=None):
        self.current_state = current_state
        self.target_state = target_state
        self.run_id = run_id
        self.extra = extra or {}
        super().__init__(
            f"Invalid transition from '{current_state}' to '{target_state}' "
            f"for run '{run_id}'"
        )


class VersionConflictError(StoreError):
    def __init__(self, run_id, expected_version, actual_version):
        self.run_id = run_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict for run '{run_id}': "
            f"expected {expected_version}, got {actual_version}"
        )
