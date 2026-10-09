"""Put the ingestion service root on sys.path so ``import app.*`` resolves
when running pytest from the repository root or the service directory.
"""
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
