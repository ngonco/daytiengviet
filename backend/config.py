from pathlib import Path
from dotenv import dotenv_values
import os

ROOT = Path(__file__).resolve().parents[1]

def settings():
    return {**dotenv_values(ROOT / '.env'), **{k: v for k, v in os.environ.items() if k.startswith(('GROQ_', 'VILAO_', 'PEXELS_', 'APP_', 'DATA_', 'FFMPEG_', 'FFPROBE_'))}}

def data_root():
    path = Path(settings().get('DATA_DIR') or './data')
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path

def binary(name):
    return settings().get(name.upper() + '_PATH') or name
