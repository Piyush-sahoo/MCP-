#!/usr/bin/env python3
"""
Personal Assistant HTTP Server
FastAPI wrapper for the Personal Assistant MCP Server
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import the original MCP server functions
from .server import (
    load_tasks, save_tasks, add_task_tool, remove_task_tool,
    get_weather_tool, search_web_tool, get_summarize_day_prompt,
    handle_list_resources, handle_read_resource, handle_list_tools,
    handle_list_prompts
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Personal Assistant MCP Server",
    description="HTTP API for Personal Assistant MCP functionality",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]

class ToolCallResponse(BaseModel):
    success: bool
    result: str
    error: Optional[str] = None

class ResourceRequest(BaseModel):
    uri: str

class ResourceResponse(BaseModel):
    success: bool
    content: str
    error: Optional[str] = None

class PromptRequest(BaseModel):
    name: str
    arguments: Dict[str, str] = {}

class PromptResponse(BaseModel):
    success: bool
    prompt: str
    error: Optional[str] = None

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "personal-assistant"}

# MCP Resources endpoints
@app.get("/resources")
async def list_resources():
    """List available resources"""
    try:
        resources = await handle_list_resources()
        return {
            "success": True,
            "resources": [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mimeType
                }
                for r in resources
            ]
        }
    except Exception as e:
        logger.error(f"Error listing resources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/resources/read", response_model=ResourceResponse)
async def read_resource(request: ResourceRequest):
    """Read a specific resource"""
    try:
        content = await handle_read_resource(request.uri)
        return ResourceResponse(success=True, content=content)
    except Exception as e:
        logger.error(f"Error reading resource {request.uri}: {e}")
        return ResourceResponse(success=False, content="", error=str(e))

# MCP Tools endpoints
@app.get("/tools")
async def list_tools():
    """List available tools"""
    try:
        tools = await handle_list_tools()
        return {
            "success": True,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema
                }
                for t in tools
            ]
        }
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    """Execute a tool"""
    try:
        if request.name == "add_task":
            result = await add_task_tool(
                request.arguments["description"],
                request.arguments["due_date"],
                request.arguments.get("priority", "medium")
            )
        elif request.name == "remove_task":
            result = await remove_task_tool(request.arguments["id"])
        elif request.name == "get_weather":
            result = await get_weather_tool(request.arguments["city"])
        elif request.name == "search_web":
            result = await search_web_tool(request.arguments["query"])
        else:
            raise ValueError(f"Unknown tool: {request.name}")
        
        return ToolCallResponse(success=True, result=result)
    except Exception as e:
        logger.error(f"Error calling tool {request.name}: {e}")
        return ToolCallResponse(success=False, result="", error=str(e))

# MCP Prompts endpoints
@app.get("/prompts")
async def list_prompts():
    """List available prompts"""
    try:
        prompts = await handle_list_prompts()
        return {
            "success": True,
            "prompts": [
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": p.arguments
                }
                for p in prompts
            ]
        }
    except Exception as e:
        logger.error(f"Error listing prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/prompts/get", response_model=PromptResponse)
async def get_prompt(request: PromptRequest):
    """Get a prompt with arguments"""
    try:
        if request.name == "summarize_day":
            prompt = await get_summarize_day_prompt(request.arguments)
        else:
            raise ValueError(f"Unknown prompt: {request.name}")
        
        return PromptResponse(success=True, prompt=prompt)
    except Exception as e:
        logger.error(f"Error getting prompt {request.name}: {e}")
        return PromptResponse(success=False, prompt="", error=str(e))

# Direct task management endpoints (convenience)
@app.get("/tasks")
async def get_tasks():
    """Get all tasks"""
    try:
        tasks = await load_tasks()
        return {
            "success": True,
            "tasks": [task.to_dict() for task in tasks]
        }
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks")
async def add_task(description: str, due_date: str, priority: str = "medium"):
    """Add a new task"""
    try:
        result = await add_task_tool(description, due_date, priority)
        return {"success": True, "message": result}
    except Exception as e:
        logger.error(f"Error adding task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task"""
    try:
        result = await remove_task_tool(task_id)
        return {"success": True, "message": result}
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_server(host: str = "127.0.0.1", port: int = 8001):
    """Run the FastAPI server"""
    logger.info(f"Starting Personal Assistant HTTP Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    run_server()