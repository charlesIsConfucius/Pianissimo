"""Locations for bundled resources and writable user data."""
import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
RESOURCE_ROOT = getattr(sys, "_MEIPASS", SOURCE_ROOT)
APP_ROOT = os.path.dirname(sys.executable) if FROZEN else SOURCE_ROOT
DATA_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Pianissimo") if FROZEN else SOURCE_ROOT
os.makedirs(DATA_ROOT, exist_ok=True)
