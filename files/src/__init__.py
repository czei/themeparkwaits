# Copyright (c) 2024-2026 Michael Czeiszperger
"""ThemeParkWaits application package.

Marks ``src`` as a package so ``import src.themeparkwaits`` (code.py's entry) and
the app's ``from src.app import ...`` imports resolve on CircuitPython, which —
unlike CPython — has no namespace packages: a directory must contain ``__init__.py``
to import as a package.

NOTE: ``.gitignore`` ignores ``__init__.py`` globally, so this file (and
``src/web/__init__.py``) are force-added (``git add -f``) like the other package
markers. They MUST stay tracked, or ``git archive``-based deploys ship a board that
can't import ``src`` / ``src.web``.
"""
