"""Guidelines Store — CPG metadata and DMN model storage.

In-memory dict for Phase 3.2, keyed by cpg_id.
CRUD operations with cascade delete.
"""

import logging

from cpg_contracts import CPGMetadata

from acp_writer.store.vector_store import VectorStore

logger = logging.getLogger(__name__)


class GuidelinesStore:
    """In-memory store for CPG metadata with cascade delete support."""

    def __init__(self, vector_store: VectorStore):
        self._guidelines: dict[str, CPGMetadata] = {}
        self._vector_store = vector_store

    def register(self, metadata: CPGMetadata) -> CPGMetadata:
        self._guidelines[metadata.cpg_id] = metadata
        logger.info("Registered guideline: %s (%s)", metadata.title, metadata.cpg_id)
        return metadata

    def get(self, cpg_id: str) -> CPGMetadata | None:
        return self._guidelines.get(cpg_id)

    def list_all(self) -> list[CPGMetadata]:
        return list(self._guidelines.values())

    def delete(self, cpg_id: str) -> bool:
        """Delete a guideline and cascade-delete associated recommendations."""
        if cpg_id not in self._guidelines:
            return False
        del self._guidelines[cpg_id]
        deleted_recs = self._vector_store.delete_by_cpg(cpg_id)
        logger.info(
            "Deleted guideline %s (cascade: %d recommendations)",
            cpg_id,
            deleted_recs,
        )
        return True

    def count(self) -> int:
        return len(self._guidelines)
