#!/usr/bin/env python3
"""
Personal Assistant MCP Server

Provides task management, weather information, and web search capabilities.
Exposes resources, tools, and prompts for personal productivity.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import httpx
from dotenv import load_dotenv

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
from shared.models import Task

# Load environment variables
load_dotenv()

# Server initialization
server = Server("personal-assistant")

# Configuration
TASKS_FILE = Path(__file__).parent / "tasks.json"
PROMPTS_DIR = Path(__file__).parent / "prompts"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Resource handlers
@server.list_resources()
async def handle_list_resources() -> List[Resource]:
    """List available resources (today://date, tasks://list)"""
    return [
        Resource(
            uri="today://date",
            name="Current Date and Time",
            description="Get the current date and time",
            mimeType="text/plain"
        ),
        Resource(
            uri="tasks://list",
            name="Task List",
            description="Get all tasks from the task list",
            mimeType="application/json"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read resource content by URI"""
    if uri == "today://date":
        current_time = datetime.utcnow()
        return current_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    elif uri == "tasks://list":
        tasks = await load_tasks()
        return json.dumps([task.to_dict() for task in tasks], indent=2)
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

# Tool handlers
@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools"""
    return [
        Tool(
            name="add_task",
            description="Add a new task to the task list",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Task description"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in ISO format (YYYY-MM-DD)"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Task priority",
                        "default": "medium"
                    }
                },
                "required": ["description", "due_date"]
            }
        ),
        Tool(
            name="remove_task",
            description="Remove a task from the task list",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Task ID to remove"
                    }
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="get_weather",
            description="Get weather information for a city",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    }
                },
                "required": ["city"]
            }
        ),
        Tool(
            name="search_web",
            description="Search the web using Tavily API",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    }
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute tool by name with arguments"""
    try:
        if name == "add_task":
            result = await add_task_tool(
                arguments["description"],
                arguments["due_date"],
                arguments.get("priority", "medium")
            )
            return [TextContent(type="text", text=result)]
        
        elif name == "remove_task":
            result = await remove_task_tool(arguments["id"])
            return [TextContent(type="text", text=result)]
        
        elif name == "get_weather":
            result = await get_weather_tool(arguments["city"])
            return [TextContent(type="text", text=result)]
        
        elif name == "search_web":
            result = await search_web_tool(arguments["query"])
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
            name="summarize_day",
            description="Generate a daily summary with tasks, weather, and search results",
            arguments=[
                {
                    "name": "city",
                    "description": "City for weather information",
                    "required": False
                },
                {
                    "name": "search_query",
                    "description": "Optional search query for additional context",
                    "required": False
                }
            ]
        )
    ]

@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, str]) -> str:
    """Get prompt template with arguments"""
    if name == "summarize_day":
        return await get_summarize_day_prompt(arguments)
    else:
        raise ValueError(f"Unknown prompt: {name}")

# Helper functions
async def load_tasks() -> List[Task]:
    """Load tasks from tasks.json file"""
    try:
        if not TASKS_FILE.exists():
            return []
        
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        tasks = []
        for task_data in data:
            try:
                task = Task.from_dict(task_data)
                tasks.append(task)
            except ValueError as e:
                print(f"Warning: Invalid task data: {e}")
                continue
        
        return tasks
    except Exception as e:
        print(f"Error loading tasks: {e}")
        return []

async def save_tasks(tasks: List[Task]) -> None:
    """Save tasks to tasks.json file"""
    try:
        # Ensure directory exists
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert tasks to dictionaries
        task_data = [task.to_dict() for task in tasks]
        
        # Write to temporary file first
        temp_file = TASKS_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False)
        
        # Atomic move
        temp_file.replace(TASKS_FILE)
    except Exception as e:
        print(f"Error saving tasks: {e}")
        raise

async def get_weather_data(city: str) -> Dict[str, Any]:
    """Fetch weather data from OpenWeather API"""
    if not OPENWEATHER_API_KEY:
        raise ValueError("OpenWeather API key not configured")
    
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

async def search_web_tavily(query: str) -> Dict[str, Any]:
    """Search web using Tavily API"""
    if not TAVILY_API_KEY:
        raise ValueError("Tavily API key not configured")
    
    url = "https://api.tavily.com/search"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": True,
        "include_images": False,
        "include_raw_content": False,
        "max_results": 5
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

# Tool implementations
async def add_task_tool(description: str, due_date: str, priority: str = "medium") -> str:
    """Add a new task"""
    try:
        # Validate due_date format
        datetime.fromisoformat(due_date)
        
        # Create new task
        task = Task.create_new(description, due_date + "T23:59:59Z", priority)
        
        # Load existing tasks
        tasks = await load_tasks()
        
        # Add new task
        tasks.append(task)
        
        # Save tasks
        await save_tasks(tasks)
        
        return f"✅ Task added successfully: '{description}' (due: {due_date}, priority: {priority})"
    
    except ValueError as e:
        return f"❌ Error adding task: {str(e)}"
    except Exception as e:
        return f"❌ Unexpected error: {str(e)}"

async def remove_task_tool(task_id: str) -> str:
    """Remove a task by ID"""
    try:
        # Load existing tasks
        tasks = await load_tasks()
        
        # Find and remove task
        original_count = len(tasks)
        tasks = [task for task in tasks if task.id != task_id]
        
        if len(tasks) == original_count:
            return f"❌ Task with ID '{task_id}' not found"
        
        # Save updated tasks
        await save_tasks(tasks)
        
        return f"✅ Task removed successfully"
    
    except Exception as e:
        return f"❌ Error removing task: {str(e)}"

async def get_weather_tool(city: str) -> str:
    """Get weather information for a city"""
    try:
        weather_data = await get_weather_data(city)
        
        # Extract relevant information
        main = weather_data["main"]
        weather = weather_data["weather"][0]
        
        temp = main["temp"]
        feels_like = main["feels_like"]
        humidity = main["humidity"]
        description = weather["description"].title()
        
        return f"🌤️ Weather in {city}:\n" \
               f"Temperature: {temp}°C (feels like {feels_like}°C)\n" \
               f"Conditions: {description}\n" \
               f"Humidity: {humidity}%"
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"❌ City '{city}' not found"
        else:
            return f"❌ Weather API error: {e.response.status_code}"
    except Exception as e:
        return f"❌ Error getting weather: {str(e)}"

async def search_web_tool(query: str) -> str:
    """Search the web using Tavily API"""
    try:
        search_results = await search_web_tavily(query)
        
        # Format results
        result_text = f"🔍 Search results for '{query}':\n\n"
        
        if "answer" in search_results and search_results["answer"]:
            result_text += f"**Answer:** {search_results['answer']}\n\n"
        
        if "results" in search_results:
            for i, result in enumerate(search_results["results"][:3], 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                content = result.get("content", "")[:200] + "..." if len(result.get("content", "")) > 200 else result.get("content", "")
                
                result_text += f"**{i}. {title}**\n"
                result_text += f"{content}\n"
                result_text += f"Source: {url}\n\n"
        
        return result_text
    
    except Exception as e:
        return f"❌ Error searching web: {str(e)}"

async def get_summarize_day_prompt(arguments: Dict[str, str]) -> str:
    """Get the summarize_day prompt with current data"""
    try:
        # Load prompt template
        prompt_file = PROMPTS_DIR / "summarize_day.txt"
        with open(prompt_file, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Get current data
        current_datetime = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Get tasks
        tasks = await load_tasks()
        tasks_text = "\n".join([
            f"- {task.description} (due: {task.due_date[:10]}, priority: {task.priority})"
            for task in tasks if not task.completed
        ])
        if not tasks_text:
            tasks_text = "No pending tasks"
        
        # Get weather if city provided
        weather_text = "Weather information not requested"
        if "city" in arguments and arguments["city"]:
            try:
                weather_data = await get_weather_data(arguments["city"])
                main = weather_data["main"]
                weather = weather_data["weather"][0]
                weather_text = f"{arguments['city']}: {weather['description'].title()}, {main['temp']}°C"
            except:
                weather_text = f"Could not get weather for {arguments['city']}"
        
        # Get search results if query provided
        search_text = "No search performed"
        if "search_query" in arguments and arguments["search_query"]:
            try:
                search_results = await search_web_tavily(arguments["search_query"])
                if "answer" in search_results and search_results["answer"]:
                    search_text = f"Search for '{arguments['search_query']}': {search_results['answer']}"
                else:
                    search_text = f"Search performed for '{arguments['search_query']}' but no clear answer found"
            except:
                search_text = f"Could not perform search for '{arguments['search_query']}'"
        
        # Substitute variables
        prompt = template.format(
            current_datetime=current_datetime,
            tasks=tasks_text,
            weather=weather_text,
            search_results=search_text
        )
        
        return prompt
    
    except Exception as e:
        return f"Error generating prompt: {str(e)}"

async def main():
    """Run the server using stdio transport"""
    logging.basicConfig(level=logging.DEBUG, filename="pa_server.log")
    logging.debug("Personal Assistant Server: Main function started.")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logging.debug("Personal Assistant Server: Stdio server started.")
            capabilities = server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={}
            )
            logging.debug(f"Personal Assistant Server: Capabilities retrieved: {capabilities}")
            init_options = InitializationOptions(
                server_name="personal-assistant",
                server_version="1.0.0",
                capabilities=capabilities,
            )
            logging.debug(f"Personal Assistant Server: Initialization options created: {init_options}")
            await server.run(
                read_stream,
                write_stream,
                init_options,
            )
            logging.debug("Personal Assistant Server: Server run completed.")
    except Exception as e:
        logging.error(f"Personal Assistant Server: An error occurred in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())