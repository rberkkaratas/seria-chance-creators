import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from abc import ABC, abstractmethod
from core.models import AppState  # noqa: F401


class TabRenderer(ABC):
    @abstractmethod
    def render(self, state: AppState) -> None: ...
