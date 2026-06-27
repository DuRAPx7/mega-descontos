import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent / "Afiliado"
sys.path.insert(0, str(APP_DIR))

from backend.server import run


if __name__ == "__main__":
    run()
