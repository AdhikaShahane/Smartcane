"""Sahayak Drishti - AI smart cane for visually impaired users.

Run on the Raspberry Pi:

    python -m smartcane                 # full system
    python -m smartcane --mock          # no hardware, type commands
    python -m smartcane --dump-serial   # see what the Arduino is sending

The decision layer lives in `guidance.py`; this module only wires the threads
together and dispatches voice commands.
"""
from __future__ import annotations

__version__ = "2.0.0"
