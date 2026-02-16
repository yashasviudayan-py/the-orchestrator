"""
Configuration management for The Orchestrator.
Loads settings from environment variables and config files.
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class RedisConfig(BaseModel):
    """Redis configuration."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ttl: int = 3600
    key_prefix: str = "orchestrator:"


class LLMConfig(BaseModel):
    """LLM configuration."""

    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b-instruct-q8_0"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.7
    max_tokens: int = 4000


class AgentPathsConfig(BaseModel):
    """Paths to external agent projects."""

    research_agent_path: str
    context_core_path: str
    pr_agent_path: str
    research_agent_url: str = "http://localhost:8000"


class OrchestratorConfig(BaseModel):
    """Main orchestrator configuration."""

    max_iterations: int = 10
    log_level: str = "INFO"


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    # Redis
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(
        default="llama3.1:8b-instruct-q8_0", alias="OLLAMA_MODEL"
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text", alias="OLLAMA_EMBEDDING_MODEL"
    )
    ollama_temperature: float = Field(default=0.7, alias="OLLAMA_TEMPERATURE")

    # Agent Paths
    research_agent_path: str = Field(alias="RESEARCH_AGENT_PATH")
    context_core_path: str = Field(alias="CONTEXT_CORE_PATH")
    pr_agent_path: str = Field(alias="PR_AGENT_PATH")
    research_agent_url: str = Field(
        default="http://localhost:8000", alias="RESEARCH_AGENT_URL"
    )

    # Orchestrator
    max_iterations: int = Field(default=10, alias="MAX_ITERATIONS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # GitHub (for PR-Agent)
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    github_username: Optional[str] = Field(default=None, alias="GITHUB_USERNAME")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config(config_path: Optional[Path] = None) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file (defaults to config/config.yaml)

    Returns:
        Configuration dict
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    return config


def get_settings() -> Settings:
    """
    Get application settings.

    Returns:
        Settings instance
    """
    return Settings()


# Singleton instance
_settings: Optional[Settings] = None


def get_cached_settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
