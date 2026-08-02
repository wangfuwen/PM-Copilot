"""
Configuration management for PM Copilot.
Loads environment variables and provides typed config access.

Supports per-agent model routing: each agent can use a different LLM
based on its capability requirements (strong reasoning vs lightweight tasks).
"""

import logging
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI default model")
    openai_model_mini: str = Field(default="gpt-4o-mini", description="OpenAI lightweight model")
    openai_embedding_model: str = Field(default="text-embedding-3-small", description="OpenAI embedding model")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = Field(default="claude-sonnet-4-20250514", description="Anthropic model name")

    # Per-Agent Model Routing (format: "provider:model_name")
    # All agents default to OpenAI for easy setup
    agent_orchestrator_model: str = Field(default="openai:gpt-4o-mini")
    agent_decision_model: str = Field(default="openai:gpt-4o")
    agent_prd_writer_model: str = Field(default="openai:gpt-4o")
    agent_stress_test_model: str = Field(default="openai:gpt-4o-mini")
    agent_critic_model: str = Field(default="openai:gpt-4o")
    agent_org_memory_model: str = Field(default="openai:gpt-4o-mini")

    # Embedding
    embedding_model: str = Field(default="openai:text-embedding-3-small")

    # Fallback
    enable_fallback: bool = Field(default=True)
    fallback_model: str = Field(default="openai:gpt-4o")

    # ChromaDB
    chroma_persist_dir: str = Field(default="./chroma_data", description="ChromaDB persistence directory")
    chroma_collection_name: str = Field(default="pm_copilot_memory", description="ChromaDB collection name")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=True)

    # Logging
    log_level: str = Field(default="INFO")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    # ---- Model Factory ----

    _llm_cache: dict[str, BaseChatModel] = {}

    def get_llm(self, agent_name: Optional[str] = None, temperature: float = 0.7, json_mode: bool = False) -> BaseChatModel:
        """
        Get the appropriate LLM for a given agent.

        Args:
            agent_name: One of 'orchestrator', 'decision', 'prd_writer',
                       'stress_test', 'critic', 'org_memory'.
                       If None, returns the default OpenAI model.
            temperature: Model temperature (default 0.7).
            json_mode: If True, force JSON output format (OpenAI only).

        Returns:
            A LangChain ChatModel instance.
        """
        if agent_name is None:
            model_spec = f"openai:{self.openai_model}"
        else:
            model_spec = getattr(self, f"agent_{agent_name}_model", f"openai:{self.openai_model}")

        cache_key = f"{model_spec}:t{temperature}:json{json_mode}"
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        provider, model_name = model_spec.split(":", 1)
        llm = self._create_llm(provider, model_name, temperature, json_mode=json_mode)
        self._llm_cache[cache_key] = llm

        logger.info(f"Agent '{agent_name or 'default'}' → {provider}/{model_name} (json_mode={json_mode})")
        return llm

    def get_fallback_llm(self, temperature: float = 0.7) -> BaseChatModel:
        """Get the fallback LLM for when the primary model fails."""
        provider, model_name = self.fallback_model.split(":", 1)
        return self._create_llm(provider, model_name, temperature)

    def get_embedding_model(self):
        """Get the embedding model instance."""
        provider, model_name = self.embedding_model.split(":", 1)
        if provider == "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model=model_name, openai_api_key=self.openai_api_key)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

    @staticmethod
    def _create_llm(provider: str, model_name: str, temperature: float, json_mode: bool = False) -> BaseChatModel:
        """Create a LangChain ChatModel from provider and model name."""
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            kwargs = dict(
                model=model_name,
                openai_api_key=settings.openai_api_key,
                temperature=temperature,
                timeout=60,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            return ChatOpenAI(**kwargs)
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name,
                anthropic_api_key=settings.anthropic_api_key,
                temperature=temperature,
                timeout=60,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def get_agent_model_summary(self) -> dict[str, str]:
        """Return a summary of which model each agent uses (for logging/debug)."""
        return {
            "orchestrator": self.agent_orchestrator_model,
            "decision": self.agent_decision_model,
            "prd_writer": self.agent_prd_writer_model,
            "stress_test": self.agent_stress_test_model,
            "critic": self.agent_critic_model,
            "org_memory": self.agent_org_memory_model,
            "embedding": self.embedding_model,
            "fallback": self.fallback_model,
        }


# Global singleton
settings = Settings()
