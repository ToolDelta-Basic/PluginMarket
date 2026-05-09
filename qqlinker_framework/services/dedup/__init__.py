# services/dedup/__init__.py
from .layered_dedup import LayeredDedup, ProcessingGuardV2
from .config import DedupConfig

__all__ = ["LayeredDedup", "ProcessingGuardV2", "DedupConfig"]