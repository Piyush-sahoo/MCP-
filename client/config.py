"""
Configuration management for MCP Learning System client.

Handles loading of environment variables, API keys, and server configurations.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class ServerConfig:
    """Configuration for an MCP server"""
    name: str
    transport: str
    host: Optional[str] = None
    port: Optional[int] = None
    command: Optional[str] = None
    args: Optional[list] = None

@dataclass
class ClientConfig:
    """Configuration for the MCP client"""
    gemini_api_key: str
    gemini_model: str
    response_temperature: float
    streamlit_port: int
    log_level: str
    servers: Dict[str, ServerConfig]

def load_config() -> ClientConfig:
    """Load configuration from environment variables"""
    # TODO: Load API keys
    gemini_api_key = os.getenv("GOOGLE_API_KEY", "")
    
    # TODO: Load client settings
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
    response_temperature = float(os.getenv("RESPONSE_TEMPERATURE", "0.7"))
    streamlit_port = int(os.getenv("STREAMLIT_PORT", "8501"))
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Get the current working directory and virtual environment python
    import sys
    python_executable = sys.executable
    
    # TODO: Load server configurations
    servers = {
        "personal_assistant": ServerConfig(
            name="personal_assistant",
            transport="http",
            host="127.0.0.1",
            port=8001
        ),
        "knowledge_base": ServerConfig(
            name="knowledge_base",
            transport="http",
            host="127.0.0.1",
            port=8002
        )
    }
    
    return ClientConfig(
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        response_temperature=response_temperature,
        streamlit_port=streamlit_port,
        log_level=log_level,
        servers=servers
    )

def validate_config(config: ClientConfig) -> bool:
    """Validate that all required configuration is present"""
    # TODO: Check for required API keys
    if not config.gemini_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    # TODO: Validate server configurations
    for server_name, server_config in config.servers.items():
        if server_config.transport == "stdio":
            if not server_config.command:
                raise ValueError(f"Command not specified for stdio server {server_name}")
        elif server_config.transport == "http":
            if not server_config.host or not server_config.port:
                raise ValueError(f"Host and port required for HTTP server {server_name}")
        else:
            raise ValueError(f"Unsupported transport type: {server_config.transport}")
    
    return True

# Global config instance
_config: Optional[ClientConfig] = None

def get_config() -> ClientConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = load_config()
        validate_config(_config)
    return _config