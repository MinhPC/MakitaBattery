import os
import sys

# `modules/` and `interfaces/` have no __init__.py (they're discovered at
# runtime via pkgutil, not imported as a regular package tree), and
# modules/makita_lxt.py does `from async_utils import run_async`. Both resolve
# only if this directory is on sys.path, same as when main.py runs directly.
sys.path.insert(0, os.path.dirname(__file__))
