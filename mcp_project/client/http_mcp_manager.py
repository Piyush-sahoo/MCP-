"""
HTTP MCP Connection Manager

Handles connections to HTTP-based MCP servers using REST API calls.
"""

import asyncio
import json
import httpx
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import logging

from client.config import ServerConfig, get_config
from client.utils import logger, RetryConfig, retry_with_exponential_backoff, CircuitBreaker
from shared.models import MCPConnection, ConnectionStatus


class HTTPMCPManager:
    """Manages HTTP connections to MCP servers"""
    
    def __init__(self):
        self.connections: Dict[str, MCPConnection] = {}
        self.base_urls: Dict[str, str] = {}
        self.capabilities_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.http_client = None
        self._client_initialized = False
    
    async def _ensure_http_client(self):
        """Ensure HTTP client is initialized and compatible with current event loop"""
        try:
            # Get current event loop ID for comparison
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)
            
            # Check if we need a new client
            need_new_client = (
                self.http_client is None or
                self.http_client.is_closed or
                getattr(self, '_current_loop_id', None) != current_loop_id
            )
            
            if need_new_client:
                # Close existing client safely
                if self.http_client is not None:
                    try:
                        if not self.http_client.is_closed:
                            await self.http_client.aclose()
                    except Exception as e:
                        logger.warning(f"Error closing existing HTTP client: {e}")
                
                # Create new client in current event loop
                self.http_client = httpx.AsyncClient(timeout=30.0)
                self._current_loop_id = current_loop_id
                self._client_initialized = True
                logger.debug(f"Created new HTTP client for event loop {current_loop_id}")
                
        except Exception as e:
            logger.error(f"Error ensuring HTTP client: {e}")
            # Fallback: always create a new client
            try:
                self.http_client = httpx.AsyncClient(timeout=30.0)
                self._current_loop_id = id(asyncio.get_running_loop())
                self._client_initialized = True
            except Exception as fallback_error:
                logger.error(f"Fallback HTTP client creation failed: {fallback_error}")
                raise

    async def initialize(self):
        """Initialize connections to all configured HTTP servers"""
        await self._ensure_http_client()
        config = get_config()
        
        for server_name, server_config in config.servers.items():
            try:
                await self.connect_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to connect to server {server_name}: {e}")
    
    async def connect_server(self, server_name: str, server_config: ServerConfig):
        """Connect to a single HTTP MCP server"""
        async with self._lock:
            try:
                # Create connection record
                connection = MCPConnection(
                    server_name=server_name,
                    transport_type="http",
                    connection_status=ConnectionStatus.CONNECTING.value,
                    host=server_config.host,
                    port=server_config.port
                )
                
                self.connections[server_name] = connection
                
                # Build base URL
                base_url = f"http://{server_config.host}:{server_config.port}"
                self.base_urls[server_name] = base_url
                
                # Test connection with health check
                await self._health_check_server(server_name)
                
                # Perform introspection
                await self._introspect_server(server_name)
                
                # Update connection status
                connection.update_status(ConnectionStatus.CONNECTED.value)
                logger.info(f"Successfully connected to HTTP server: {server_name} at {base_url}")
                
            except Exception as e:
                if server_name in self.connections:
                    self.connections[server_name].update_status(
                        ConnectionStatus.ERROR.value,
                        str(e)
                    )
                logger.error(f"Failed to connect to server {server_name}: {e}")
                raise
    
    async def _health_check_server(self, server_name: str):
        """Perform health check on a server"""
        await self._ensure_http_client()
        base_url = self.base_urls[server_name]
        
        try:
            response = await self.http_client.get(f"{base_url}/health")
            response.raise_for_status()
            
            health_data = response.json()
            logger.info(f"Health check for {server_name}: {health_data}")
            
        except Exception as e:
            logger.error(f"Health check failed for {server_name}: {e}")
            raise
    
    @retry_with_exponential_backoff(RetryConfig(max_attempts=3))
    async def _introspect_server(self, server_name: str):
        """Perform introspection on a server to discover capabilities"""
        await self._ensure_http_client()
        base_url = self.base_urls[server_name]
        capabilities = {}
        
        try:
            # Get tools
            tools_response = await self.http_client.get(f"{base_url}/tools")
            tools_response.raise_for_status()
            tools_data = tools_response.json()
            capabilities["tools"] = tools_data.get("tools", [])
            
            # Get resources
            resources_response = await self.http_client.get(f"{base_url}/resources")
            resources_response.raise_for_status()
            resources_data = resources_response.json()
            capabilities["resources"] = resources_data.get("resources", [])
            
            # Get prompts
            prompts_response = await self.http_client.get(f"{base_url}/prompts")
            prompts_response.raise_for_status()
            prompts_data = prompts_response.json()
            capabilities["prompts"] = prompts_data.get("prompts", [])
            
            # Cache capabilities
            self.capabilities_cache[server_name] = capabilities
            
            # Update connection record
            if server_name in self.connections:
                self.connections[server_name].capabilities = capabilities
            
            logger.info(f"Introspected server {server_name}: "
                       f"{len(capabilities.get('tools', []))} tools, "
                       f"{len(capabilities.get('resources', []))} resources, "
                       f"{len(capabilities.get('prompts', []))} prompts")
        
        except Exception as e:
            logger.error(f"Failed to introspect server {server_name}: {e}")
            raise
    
    async def disconnect_server(self, server_name: str):
        """Disconnect from a server"""
        async with self._lock:
            try:
                # Update connection status
                if server_name in self.connections:
                    self.connections[server_name].update_status(
                        ConnectionStatus.DISCONNECTED.value
                    )
                
                # Clear from base URLs
                if server_name in self.base_urls:
                    del self.base_urls[server_name]
                
                # Clear capabilities cache
                if server_name in self.capabilities_cache:
                    del self.capabilities_cache[server_name]
                
                logger.info(f"Disconnected from server: {server_name}")
                
            except Exception as e:
                logger.error(f"Error disconnecting from server {server_name}: {e}")
    
    async def disconnect_all(self):
        """Disconnect from all servers"""
        for server_name in list(self.base_urls.keys()):
            await self.disconnect_server(server_name)
        
        # Close HTTP client if it exists and is not already closed
        if self.http_client is not None and not self.http_client.is_closed:
            await self.http_client.aclose()
            self.http_client = None
            self._client_initialized = False
    
    def get_connection_status(self, server_name: str) -> Optional[MCPConnection]:
        """Get connection status for a server"""
        return self.connections.get(server_name)
    
    def get_all_connections(self) -> Dict[str, MCPConnection]:
        """Get all connection statuses"""
        return self.connections.copy()
    
    def is_server_connected(self, server_name: str) -> bool:
        """Check if a server is connected"""
        connection = self.connections.get(server_name)
        return connection is not None and connection.is_connected()
    
    def get_server_capabilities(self, server_name: str) -> Dict[str, Any]:
        """Get cached capabilities for a server"""
        return self.capabilities_cache.get(server_name, {})
    
    def get_all_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """Get capabilities for all connected servers"""
        return self.capabilities_cache.copy()
    
    @CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on a specific server"""
        await self._ensure_http_client()
        
        if not self.is_server_connected(server_name):
            raise ConnectionError(f"Server {server_name} is not connected")
        
        base_url = self.base_urls[server_name]
        
        try:
            payload = {
                "name": tool_name,
                "arguments": arguments
            }
            
            response = await self.http_client.post(
                f"{base_url}/tools/call",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Update last ping time
            if server_name in self.connections:
                self.connections[server_name].last_ping = datetime.utcnow()
            
            if result.get("success"):
                return result.get("result", "")
            else:
                raise RuntimeError(result.get("error", "Unknown error"))
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name} on server {server_name}: {e}")
            # Update connection status on error
            if server_name in self.connections:
                self.connections[server_name].update_status(
                    ConnectionStatus.ERROR.value,
                    str(e)
                )
            raise
    
    @CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from a specific server"""
        await self._ensure_http_client()
        
        if not self.is_server_connected(server_name):
            raise ConnectionError(f"Server {server_name} is not connected")
        
        base_url = self.base_urls[server_name]
        
        try:
            payload = {"uri": uri}
            
            response = await self.http_client.post(
                f"{base_url}/resources/read",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Update last ping time
            if server_name in self.connections:
                self.connections[server_name].last_ping = datetime.utcnow()
            
            if result.get("success"):
                return result.get("content", "")
            else:
                raise RuntimeError(result.get("error", "Unknown error"))
            
        except Exception as e:
            logger.error(f"Error reading resource {uri} from server {server_name}: {e}")
            # Update connection status on error
            if server_name in self.connections:
                self.connections[server_name].update_status(
                    ConnectionStatus.ERROR.value,
                    str(e)
                )
            raise
    
    @CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    async def get_prompt(self, server_name: str, prompt_name: str, arguments: Dict[str, str] = None) -> str:
        """Get a prompt from a specific server"""
        await self._ensure_http_client()
        
        if not self.is_server_connected(server_name):
            raise ConnectionError(f"Server {server_name} is not connected")
        
        base_url = self.base_urls[server_name]
        
        try:
            payload = {
                "name": prompt_name,
                "arguments": arguments or {}
            }
            
            response = await self.http_client.post(
                f"{base_url}/prompts/get",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Update last ping time
            if server_name in self.connections:
                self.connections[server_name].last_ping = datetime.utcnow()
            
            if result.get("success"):
                return result.get("prompt", "")
            else:
                raise RuntimeError(result.get("error", "Unknown error"))
            
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_name} from server {server_name}: {e}")
            # Update connection status on error
            if server_name in self.connections:
                self.connections[server_name].update_status(
                    ConnectionStatus.ERROR.value,
                    str(e)
                )
            raise
    
    async def refresh_capabilities(self, server_name: str = None):
        """Refresh capabilities for one or all servers"""
        if server_name:
            if self.is_server_connected(server_name):
                await self._introspect_server(server_name)
        else:
            for name in self.base_urls.keys():
                if self.is_server_connected(name):
                    try:
                        await self._introspect_server(name)
                    except Exception as e:
                        logger.error(f"Failed to refresh capabilities for {name}: {e}")
    
    async def health_check(self):
        """Perform health check on all connections"""
        await self._ensure_http_client()
        for server_name, connection in self.connections.items():
            if connection.is_connected():
                try:
                    await self._health_check_server(server_name)
                    connection.last_ping = datetime.utcnow()
                except Exception as e:
                    logger.warning(f"Health check failed for {server_name}: {e}")
                    connection.update_status(ConnectionStatus.ERROR.value, str(e))
    
    def get_available_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available tools from all connected servers"""
        all_tools = {}
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                all_tools[server_name] = capabilities.get("tools", [])
        return all_tools
    
    def get_available_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available resources from all connected servers"""
        all_resources = {}
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                all_resources[server_name] = capabilities.get("resources", [])
        return all_resources
    
    def get_available_prompts(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available prompts from all connected servers"""
        all_prompts = {}
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                all_prompts[server_name] = capabilities.get("prompts", [])
        return all_prompts
    
    def find_tool(self, tool_name: str) -> Optional[str]:
        """Find which server provides a specific tool"""
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                tools = capabilities.get("tools", [])
                for tool in tools:
                    if tool.get("name") == tool_name:
                        return server_name
        return None
    
    def find_resource(self, uri: str) -> Optional[str]:
        """Find which server provides a specific resource"""
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                resources = capabilities.get("resources", [])
                for resource in resources:
                    if resource.get("uri") == uri:
                        return server_name
        return None
    
    def find_prompt(self, prompt_name: str) -> Optional[str]:
        """Find which server provides a specific prompt"""
        for server_name, capabilities in self.capabilities_cache.items():
            if self.is_server_connected(server_name):
                prompts = capabilities.get("prompts", [])
                for prompt in prompts:
                    if prompt.get("name") == prompt_name:
                        return server_name
        return None


# Global HTTP MCP manager instance
_http_mcp_manager: Optional[HTTPMCPManager] = None

async def get_http_mcp_manager() -> HTTPMCPManager:
    """Get the global HTTP MCP manager instance"""
    global _http_mcp_manager
    if _http_mcp_manager is None:
        _http_mcp_manager = HTTPMCPManager()
        await _http_mcp_manager.initialize()
    return _http_mcp_manager