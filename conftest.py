"""Shared test fixtures for the Yandex Ynison plugin."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# Stub out librosa (and its heavy deps: numba, llvmlite) so that
# importing MA server doesn't fail when llvmlite can't compile.
for _mod in ("llvmlite", "llvmlite.binding", "numba", "numba.core", "librosa"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock(spec=ModuleType)
