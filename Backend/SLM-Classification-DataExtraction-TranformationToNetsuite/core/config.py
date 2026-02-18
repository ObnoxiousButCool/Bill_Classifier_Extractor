"""
Configuration management using Pydantic Settings.
Loads environment variables and validates required settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database Configuration
    DATABASE_URL: str
    
    # LLM Configuration
    LLM_API_KEY: str
    LLM_MODEL: str = "llama3.1:8b"
    LLM_BASE_URL: Optional[str] = "http://localhost:11434/v1"  # Ollama default
    
    # Application Settings
    DEBUG: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
