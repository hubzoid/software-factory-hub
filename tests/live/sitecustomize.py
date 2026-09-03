"""Loads the live-run stand-ins (factory_live.py) into every Python process
started with this folder on PYTHONPATH and FACTORY_LIVE_SANDBOX or
FACTORY_LIVE_GITHUB set. For the proof run on a machine without a container
runtime. Never on a real hub's path."""
import os
import sys

if os.environ.get("FACTORY_LIVE_SANDBOX") or os.environ.get("FACTORY_LIVE_GITHUB"):
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))      # the hub root, for tests.conftest
    sys.path.insert(0, _here)
    import factory_live

    factory_live.install()
