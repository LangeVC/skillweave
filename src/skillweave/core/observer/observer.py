import os
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
import fcntl

@dataclass(frozen=True)
class Lease:
    id: str
    owner: str

@dataclass(frozen=True)
class ObserverState:
    lease: Optional[Lease]
    journal_offset: int

class ReadOnlyError(Exception):
    pass

class ReadOnlyObserver:
    """
    A persistent, read-only observer that supports Leases and Journal-Offsets.
    Mutation of state is technically denied (raises ReadOnlyError).
    """

    def __init__(self, storage_path: str):
        self._storage_path = storage_path
        self._state = self._load_state()

    def _load_state(self) -> ObserverState:
        if not os.path.exists(self._storage_path):
            return ObserverState(lease=None, journal_offset=0)
            
        with open(self._storage_path, 'r') as f:
            try:
                data = json.load(f)
                lease_data = data.get('lease')
                lease = Lease(**lease_data) if lease_data else None
                return ObserverState(
                    lease=lease,
                    journal_offset=data.get('journal_offset', 0)
                )
            except json.JSONDecodeError:
                return ObserverState(lease=None, journal_offset=0)

    @property
    def state(self) -> ObserverState:
        return self._state

    @property
    def current_offset(self) -> int:
        return self._state.journal_offset

    @property
    def current_lease(self) -> Optional[Lease]:
        return self._state.lease

    def mutate_state(self, *args, **kwargs):
        raise ReadOnlyError("Mutation of state is technically denied in read-only observer mode.")

    def update_offset(self, offset: int):
        raise ReadOnlyError("Cannot mutate offset directly on ReadOnlyObserver.")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_storage_path', '_state'):
            super().__setattr__(name, value)
        else:
            raise ReadOnlyError(f"Cannot mutate attribute '{name}' on ReadOnlyObserver.")
