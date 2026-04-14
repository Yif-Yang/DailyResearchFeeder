from __future__ import annotations

from abc import ABC, abstractmethod

from dailyresearchfeeder.models import CandidateItem


class BaseSource(ABC):
    @abstractmethod
    async def fetch(self, **kwargs) -> list[CandidateItem]:
        raise NotImplementedError