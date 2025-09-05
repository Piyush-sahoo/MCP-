#!/usr/bin/env python3
"""
Knowledge Base HTTP Server
FastAPI wrapper for the Knowledge Base MCP Server
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
    load_all_notes, search_notes_by_keyword, get_note_by_id,
    search_notes_tool, summarize_text_tool, get_faq_answer_prompt,
    handle_list_resources, handle_read_resource, handle_list_tools,
    handle_list_prompts
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Knowledge Base MCP Server",
    description="HTTP API for Knowledge Base MCP functionality",
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

class SearchRequest(BaseModel):
    keyword: str
    max_results: int = 5

class SearchResponse(BaseModel):
    success: bool
    notes: List[Dict[str, Any]]
    error: Optional[str] = None

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "knowledge-base"}

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
        if request.name == "search_notes":
            result = await search_notes_tool(
                request.arguments["keyword"],
                request.arguments.get("max_results", 5)
            )
        elif request.name == "summarize_text":
            result = await summarize_text_tool(request.arguments["note_id"])
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
        if request.name == "faq_answer":
            prompt = await get_faq_answer_prompt(request.arguments)
        else:
            raise ValueError(f"Unknown prompt: {request.name}")
        
        return PromptResponse(success=True, prompt=prompt)
    except Exception as e:
        logger.error(f"Error getting prompt {request.name}: {e}")
        return PromptResponse(success=False, prompt="", error=str(e))

# Direct note management endpoints (convenience)
@app.get("/notes")
async def get_all_notes():
    """Get all notes"""
    try:
        notes = await load_all_notes()
        return {
            "success": True,
            "notes": [note.to_dict() for note in notes]
        }
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notes/search", response_model=SearchResponse)
async def search_notes(request: SearchRequest):
    """Search notes by keyword"""
    try:
        notes = await search_notes_by_keyword(request.keyword, request.max_results)
        return SearchResponse(
            success=True,
            notes=[note.to_dict() for note in notes]
        )
    except Exception as e:
        logger.error(f"Error searching notes: {e}")
        return SearchResponse(success=False, notes=[], error=str(e))

@app.get("/notes/{note_id}")
async def get_note(note_id: str):
    """Get a specific note by ID"""
    try:
        note = await get_note_by_id(note_id)
        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID '{note_id}' not found")
        
        return {
            "success": True,
            "note": note.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting note {note_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/notes/{note_id}/summary")
async def get_note_summary(note_id: str):
    """Get a summary of a specific note"""
    try:
        result = await summarize_text_tool(note_id)
        return {"success": True, "summary": result}
    except Exception as e:
        logger.error(f"Error getting note summary {note_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_server(host: str = "127.0.0.1", port: int = 8002):
    """Run the FastAPI server"""
    logger.info(f"Starting Knowledge Base HTTP Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    run_server()