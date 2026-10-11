"""Put src/ on the path so the tests import the pipeline's modules the way its scripts do."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
