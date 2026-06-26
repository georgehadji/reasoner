"""Port interfaces for hexagonal architecture.

Ports define abstract interfaces that the application layer depends on,
while adapters (in infrastructure/) implement them.
"""

from reasoner.core.ports.translation_port import TranslationPort, TranslationResult

__all__ = ["TranslationPort", "TranslationResult"]
