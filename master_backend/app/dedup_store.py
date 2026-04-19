"""
Sequence-number based deduplication (CLAUDE.md §1 Idempotent Ingestion).
Keyed by (device_id, session_id, sequence_number).
Cleared when a session ends.
"""


class DedupStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str, int]] = set()

    def is_duplicate(self, device_id: str, session_id: str, seq: int) -> bool:
        return (device_id, session_id, seq) in self._seen

    def add(self, device_id: str, session_id: str, seq: int) -> None:
        self._seen.add((device_id, session_id, seq))

    def clear(self) -> None:
        self._seen.clear()

    @property
    def size(self) -> int:
        return len(self._seen)


dedup = DedupStore()
