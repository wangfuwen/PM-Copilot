from pydantic_settings import BaseSettings
from pydantic import Field

class TestSettings(BaseSettings):
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o")
    openai_model_mini: str = Field(default="gpt-4o-mini")
    agent_orchestrator_model: str = Field(default="openai:gpt-4o-mini")
    agent_decision_model: str = Field(default="openai:gpt-4o")
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}

s = TestSettings()
print(f"OPENAI_API_KEY: {'SET' if s.openai_api_key else 'EMPTY'}")
print(f"Key prefix: {s.openai_api_key[:15] if s.openai_api_key else 'NONE'}...")
print(f"orchestrator model: {s.agent_orchestrator_model}")
print(f"decision model: {s.agent_decision_model}")
