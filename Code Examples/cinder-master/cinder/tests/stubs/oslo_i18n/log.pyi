# Stubs for oslo_i18n.log (Python 3)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from logging import handlers
from typing import Any, Optional

class TranslationHandler(handlers.MemoryHandler):
    locale: Any = ...
    def __init__(self, locale: Optional[Any] = ..., target: Optional[Any] = ...) -> None: ...
    def setFormatter(self, fmt: Any) -> None: ...
    def emit(self, record: Any) -> None: ...
