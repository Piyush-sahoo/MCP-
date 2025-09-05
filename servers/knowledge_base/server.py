#!/usr/bin/env python3
"""
Knowledge Base MCP Server

Manages local knowledge base with search and summarization capabilities.
Supports Markdown and JSON note formats with full-text search.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from collections import defaultdict

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    Prompt,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from shared.models import Note

# Server initialization
server = Server("knowledge-base")

# Configuration
NOTES_DIR = Path(__file__).parent / "notes"
PROMPTS_DIR = Path(__file__).parent / "prompts"

# In-memory cache for notes
_notes_cache: List[Note] = []
_cache_last_updated: Optional[datetime] = None

# Resource handlers
@server.list_resources()
async def handle_list_resources() -> List[Resource]:
    """List available resources (notes://all)"""
    return [
        Resource(
            uri="notes://all",
            name="All Notes",
            description="Get all notes from the knowledge base",
            mimeType="application/json"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read resource content by URI"""
    if uri == "notes://all":
        notes = await load_all_notes()
        return json.dumps([note.to_dict() for note in notes], indent=2)
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

# Tool handlers
@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools"""
    return [
        Tool(
            name="search_notes",
            description="Search notes by keyword with relevance scoring",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keyword to search for in notes"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="summarize_text",
            description="Get a summary of a specific note by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "description": "ID of the note to summarize"
                    }
                },
                "required": ["note_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute tool by name with arguments"""
    try:
        if name == "search_notes":
            result = await search_notes_tool(
                arguments["keyword"],
                arguments.get("max_results", 5)
            )
            return [TextContent(type="text", text=result)]
        
        elif name == "summarize_text":
            result = await summarize_text_tool(arguments["note_id"])
            return [TextContent(type="text", text=result)]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    except Exception as e:
        error_msg = f"Error executing tool {name}: {str(e)}"
        return [TextContent(type="text", text=error_msg)]

# Prompt handlers
@server.list_prompts()
async def handle_list_prompts() -> List[Prompt]:
    """List available prompts"""
    return [
        Prompt(
            name="faq_answer",
            description="Generate FAQ-style answers from knowledge base content",
            arguments=[
                {
                    "name": "question",
                    "description": "The question to answer",
                    "required": True
                },
                {
                    "name": "search_keywords",
                    "description": "Keywords to search for relevant content",
                    "required": False
                }
            ]
        )
    ]

@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, str]) -> str:
    """Get prompt template with arguments"""
    if name == "faq_answer":
        return await get_faq_answer_prompt(arguments)
    else:
        raise ValueError(f"Unknown prompt: {name}")

# Helper functions
async def load_all_notes() -> List[Note]:
    """Load all notes from the notes directory"""
    global _notes_cache, _cache_last_updated
    
    try:
        # Check if cache needs refresh
        if _cache_last_updated is None or should_refresh_cache():
            _notes_cache = []
            
            if not NOTES_DIR.exists():
                NOTES_DIR.mkdir(parents=True, exist_ok=True)
                return []
            
            # Load all note files
            for file_path in NOTES_DIR.iterdir():
                if file_path.is_file() and file_path.suffix in ['.md', '.json']:
                    try:
                        note = await load_note_from_file(file_path)
                        if note:
                            _notes_cache.append(note)
                    except Exception as e:
                        print(f"Warning: Could not load note {file_path}: {e}")
                        continue
            
            _cache_last_updated = datetime.utcnow()
        
        return _notes_cache
    
    except Exception as e:
        print(f"Error loading notes: {e}")
        return []

def should_refresh_cache() -> bool:
    """Check if cache should be refreshed based on file modification times"""
    if not _cache_last_updated:
        return True
    
    try:
        for file_path in NOTES_DIR.iterdir():
            if file_path.is_file() and file_path.suffix in ['.md', '.json']:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime > _cache_last_updated:
                    return True
        return False
    except:
        return True

async def load_note_from_file(file_path: Path) -> Optional[Note]:
    """Load a single note from file"""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        if file_path.suffix == '.json':
            # Handle JSON notes
            data = json.loads(content)
            title = data.get('title', file_path.stem)
            note_content = data.get('content', content)
        else:
            # Handle Markdown notes
            title = extract_title_from_markdown(content) or file_path.stem.replace('_', ' ').replace('-', ' ').title()
            note_content = content
        
        note = Note.from_file(str(file_path), note_content, title)
        return note
    
    except Exception as e:
        print(f"Error loading note from {file_path}: {e}")
        return None

def extract_title_from_markdown(content: str) -> Optional[str]:
    """Extract title from markdown content"""
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('# '):
            return line[2:].strip()
    return None

async def search_notes_by_keyword(keyword: str, max_results: int = 5) -> List[Note]:
    """Search notes by keyword with relevance scoring"""
    notes = await load_all_notes()
    
    # Calculate relevance scores
    scored_notes = []
    for note in notes:
        score = note.search_relevance(keyword)
        if score > 0:
            scored_notes.append((note, score))
    
    # Sort by relevance score (descending)
    scored_notes.sort(key=lambda x: x[1], reverse=True)
    
    # Return top results
    return [note for note, score in scored_notes[:max_results]]

async def get_note_by_id(note_id: str) -> Optional[Note]:
    """Get specific note by ID"""
    notes = await load_all_notes()
    for note in notes:
        if note.id == note_id:
            return note
    return None

# Tool implementations
async def search_notes_tool(keyword: str, max_results: int = 5) -> str:
    """Search notes by keyword"""
    try:
        notes = await search_notes_by_keyword(keyword, max_results)
        
        if not notes:
            return f"🔍 No notes found containing '{keyword}'"
        
        result = f"🔍 Found {len(notes)} note(s) containing '{keyword}':\n\n"
        
        for i, note in enumerate(notes, 1):
            # Calculate relevance score for display
            score = note.search_relevance(keyword)
            
            result += f"**{i}. {note.title}**\n"
            result += f"File: {Path(note.file_path).name}\n"
            result += f"Tags: {', '.join(note.tags) if note.tags else 'None'}\n"
            result += f"Word count: {note.word_count}\n"
            result += f"Relevance: {score:.1f}\n"
            
            # Show a snippet of content
            content_snippet = note.content[:200] + "..." if len(note.content) > 200 else note.content
            result += f"Preview: {content_snippet}\n\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error searching notes: {str(e)}"

async def summarize_text_tool(note_id: str) -> str:
    """Summarize a specific note by ID"""
    try:
        note = await get_note_by_id(note_id)
        
        if not note:
            return f"❌ Note with ID '{note_id}' not found"
        
        # Generate a simple summary
        summary = generate_simple_summary(note.content)
        
        result = f"📄 **Summary of '{note.title}'**\n\n"
        result += f"**File:** {Path(note.file_path).name}\n"
        result += f"**Word count:** {note.word_count}\n"
        result += f"**Tags:** {', '.join(note.tags) if note.tags else 'None'}\n"
        result += f"**Created:** {note.created_at[:10]}\n\n"
        result += f"**Summary:**\n{summary}\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error summarizing note: {str(e)}"

def generate_simple_summary(content: str, max_sentences: int = 3) -> str:
    """Generate a simple extractive summary"""
    # Split into sentences
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= max_sentences:
        return '. '.join(sentences) + '.'
    
    # Simple scoring based on sentence length and position
    scored_sentences = []
    for i, sentence in enumerate(sentences):
        score = 0
        
        # Prefer sentences with moderate length
        if 10 <= len(sentence.split()) <= 30:
            score += 2
        
        # Prefer sentences near the beginning
        if i < len(sentences) * 0.3:
            score += 1
        
        # Prefer sentences with common keywords
        common_words = ['important', 'key', 'main', 'primary', 'essential', 'crucial']
        for word in common_words:
            if word.lower() in sentence.lower():
                score += 1
        
        scored_sentences.append((sentence, score))
    
    # Sort by score and take top sentences
    scored_sentences.sort(key=lambda x: x[1], reverse=True)
    top_sentences = [s[0] for s in scored_sentences[:max_sentences]]
    
    # Reorder by original position
    original_order = []
    for sentence in sentences:
        if sentence in top_sentences:
            original_order.append(sentence)
            if len(original_order) == max_sentences:
                break
    
    return '. '.join(original_order) + '.'

async def get_faq_answer_prompt(arguments: Dict[str, str]) -> str:
    """Get the FAQ answer prompt with relevant notes"""
    try:
        # Load prompt template
        prompt_file = PROMPTS_DIR / "faq_answer.txt"
        with open(prompt_file, 'r', encoding='utf-8') as f:
            template = f.read()
        
        question = arguments.get("question", "")
        search_keywords = arguments.get("search_keywords", "")
        
        # If no search keywords provided, extract from question
        if not search_keywords and question:
            # Simple keyword extraction from question
            words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
            # Remove common question words
            stop_words = {'what', 'how', 'why', 'when', 'where', 'who', 'which', 'can', 'does', 'will', 'should'}
            keywords = [w for w in words if w not in stop_words]
            search_keywords = ' '.join(keywords[:3])  # Use top 3 keywords
        
        # Search for relevant notes
        relevant_notes_text = "No relevant notes found"
        if search_keywords:
            try:
                notes = await search_notes_by_keyword(search_keywords, 3)
                if notes:
                    relevant_notes_text = ""
                    for note in notes:
                        relevant_notes_text += f"**{note.title}**\n"
                        relevant_notes_text += f"{note.content[:500]}...\n\n" if len(note.content) > 500 else f"{note.content}\n\n"
            except:
                relevant_notes_text = "Error retrieving relevant notes"
        
        # Substitute variables in template
        prompt = template.format(
            question=question,
            relevant_notes=relevant_notes_text
        )
        
        return prompt
    
    except Exception as e:
        return f"Error generating FAQ prompt: {str(e)}"

async def main():
    """Run the server using stdio transport"""
    logging.basicConfig(level=logging.DEBUG, filename="kb_server.log")
    logging.debug("Knowledge Base Server: Main function started.")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logging.debug("Knowledge Base Server: Stdio server started.")
            capabilities = server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={}
            )
            logging.debug(f"Knowledge Base Server: Capabilities retrieved: {capabilities}")
            init_options = InitializationOptions(
                server_name="knowledge-base",
                server_version="1.0.0",
                capabilities=capabilities,
            )
            logging.debug(f"Knowledge Base Server: Initialization options created: {init_options}")
            await server.run(
                read_stream,
                write_stream,
                init_options,
            )
            logging.debug("Knowledge Base Server: Server run completed.")
    except Exception as e:
        logging.error(f"Knowledge Base Server: An error occurred in main: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())