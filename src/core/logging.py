"""Legacy module placeholder.

This repository used to provide a monolithic `src.core.logging` module at
`src/core/logging.py`.

It has been replaced by the `src.core.logging` *package* (directory:
`src/core/logging/`). The new package has no import-time configuration side
effects; entrypoints must explicitly call
`src.core.logging.configuration.configure_root_logging()`.

This file remains only to fail fast if any legacy import paths survive.
"""

raise ImportError(
    "Legacy module src/core/logging.py is removed. Import from src.core.logging (package)."
)
