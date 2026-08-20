import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 9999
    VLLM_API_BASE: str = "http://192.168.11.86:11434/v1"
    VLLM_MODEL: str = "gemma4:31b"
    FALLBACK_VLLM_ENDPOINTS: List[str] = [
        "http://192.168.11.86:11434/v1",
        "http://192.168.11.86:8000/v1",
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:8000/v1"
    ]
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@192.168.11.86:5432/ats_engineering"
    REDIS_URL: str = "redis://192.168.11.86:6380/0"
    DEFAULT_WORKSTATION_IP: str = "192.168.11.150"
    DEFAULT_USER_NAME: str = "Koustubh Deodhar"
    EXPORT_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "exports"))
    STATIC_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
os.makedirs(settings.EXPORT_DIR, exist_ok=True)
os.makedirs(settings.STATIC_DIR, exist_ok=True)
