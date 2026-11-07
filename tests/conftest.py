"""Config compartida: aislar env vars antes de importar app."""
import os, sys
from pathlib import Path

# Permite `import app` sin instalar
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ARKI_BRIDGE_TOKEN", "test-bridge-token-32-chars-minimum")
os.environ.setdefault("ARKI_IDENTITY_INTERNAL_KEY", "test-internal-key-32-chars-minimum")
os.environ.setdefault("SICL_WEB_BASE", "http://127.0.0.1:8000")
os.environ.setdefault("ARKI_SICL_WEB", "/tmp/arki-test-sicl-web")
os.environ.setdefault("ARKI_SICL_CORE", "/tmp/arki-test-sicl-core")
