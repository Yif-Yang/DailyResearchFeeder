from __future__ import annotations

from abc import ABC, abstractmethod

from dailyresearchfeeder.models import CandidateItem


class SourceFetchError(RuntimeError):
    def __init__(self, source_name: str, message: str):
        super().__init__(f"{source_name}: {message}")
        self.source_name = source_name


class BaseSource(ABC):
    @abstractmethod
    async def fetch(self, **kwargs) -> list[CandidateItem]:
        raise NotImplementedError