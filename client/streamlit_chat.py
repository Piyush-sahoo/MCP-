#!/usr/bin/env python3
"""
Streamlit Chat Client with Gemini and MCP Integration

Provides a web-based chat interface that connects to MCP servers,
uses Gemini for natural language processing, and dynamically
executes tools and resources based on user requests.
"""

import asyncio
import streamlit as st
from typing import Dict, List, Any, Optional
import google.generativeai as genai
from datetime import datetime
import json
import re
import traceback
import sys
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

from client.http_mcp_manager import get_http_mcp_manager
from client.config import get_config
from client.utils import logger, sanitize_input, format_mcp_response

def initialize_session_state():
    """Initialize Streamlit session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "mcp_manager" not in st.session_state:
        st.session_state.mcp_manager = None
    
    if "gemini_model" not in st.session_state:
        st.session_state.gemini_model = None
    
    if "response_mode" not in st.session_state:
        st.session_state.response_mode = "deterministic"

def setup_gemini():
    """Initialize Gemini API client"""
    try:
        config = get_config()
        if not config.gemini_api_key:
            st.error("Gemini API key not configured. Please set GOOGLE_API_KEY in your .env file.")
            return None
        
        genai.configure(api_key=config.gemini_api_key)
        model = genai.GenerativeModel(config.gemini_model)
        return model
    except Exception as e:
        st.error(f"Failed to initialize Gemini: {e}")
        return None

async def setup_mcp_connections():
    """Initialize connections to MCP servers"""
    try:
        mcp_manager = await get_http_mcp_manager()
        return mcp_manager
    except Exception as e:
        st.error(f"Failed to initialize MCP connections: {e}")
        logger.error(f"MCP initialization error: {e}")
        return None

def display_chat_messages():
    """Display chat message history"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

async def handle_inspect_command(mcp_manager) -> str:
    """Handle /inspect command to show server capabilities"""
    try:
        connections = mcp_manager.get_all_connections()
        capabilities = mcp_manager.get_all_capabilities()
        
        result = "🔍 **MCP Server Inspection**\n\n"
        
        for server_name, connection in connections.items():
            result += f"## {server_name.title()} Server\n"
            result += f"**Status:** {connection.connection_status}\n"
            result += f"**Transport:** {connection.transport_type}\n"
            
            if connection.last_ping:
                result += f"**Last Ping:** {connection.last_ping.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if connection.error_message:
                result += f"**Error:** {connection.error_message}\n"
            
            server_caps = capabilities.get(server_name, {})
            
            # Tools
            tools = server_caps.get("tools", [])
            result += f"**Tools ({len(tools)}):**\n"
            for tool in tools:
                result += f"- `{tool.get('name', 'Unknown')}`: {tool.get('description', 'No description')}\n"
            
            # Resources
            resources = server_caps.get("resources", [])
            result += f"**Resources ({len(resources)}):**\n"
            for resource in resources:
                result += f"- `{resource.get('uri', 'Unknown')}`: {resource.get('description', 'No description')}\n"
            
            # Prompts
            prompts = server_caps.get("prompts", [])
            result += f"**Prompts ({len(prompts)}):**\n"
            for prompt in prompts:
                result += f"- `{prompt.get('name', 'Unknown')}`: {prompt.get('description', 'No description')}\n"
            
            result += "\n"
        
        return result
    
    except Exception as e:
        return f"❌ Error inspecting servers: {str(e)}"

async def process_user_message(user_input: str, mcp_manager, gemini_model, response_mode: str) -> str:
    """Process user message and generate response"""
    try:
        # Sanitize input
        user_input = sanitize_input(user_input)
        
        # Check for special commands
        if user_input.lower().startswith('/inspect'):
            return await handle_inspect_command(mcp_manager)
        
        # Use Gemini to interpret user intent and generate MCP calls
        response = await interpret_and_execute(user_input, mcp_manager, gemini_model, response_mode)
        return response
    
    except Exception as e:
        logger.error(f"Error processing user message: {e}")
        return f"❌ Error processing your request: {str(e)}"

async def interpret_and_execute(user_input: str, mcp_manager, gemini_model, response_mode: str) -> str:
    """Use Gemini to interpret user intent and execute MCP operations"""
    try:
        # Get available capabilities
        tools = mcp_manager.get_available_tools()
        resources = mcp_manager.get_available_resources()
        prompts = mcp_manager.get_available_prompts()
        
        # Create context for Gemini
        context = create_mcp_context(tools, resources, prompts)
        
        # Generate system prompt
        system_prompt = f"""You are an AI assistant that can help users by calling MCP (Model Context Protocol) tools and accessing resources.

Available MCP capabilities:
{context}

IMPORTANT: You must respond with ONLY a valid JSON object. Do not include any other text, explanations, or markdown formatting.

When a user makes a request, analyze their intent and determine if you need to:
1. Call MCP tools to perform actions
2. Read MCP resources to get information
3. Use MCP prompts for structured responses
4. Provide a direct response without MCP calls

If you need to use MCP capabilities, respond with ONLY this JSON format:
{{
    "action": "mcp_call",
    "operations": [
        {{
            "type": "tool",
            "server": "server_name",
            "name": "tool_name",
            "arguments": {{"key": "value"}}
        }}
    ],
    "explanation": "Brief explanation of what you're doing"
}}

If you can respond directly without MCP calls, use ONLY this JSON format:
{{
    "action": "direct_response",
    "response": "Your direct response here"
}}

Examples:
- For weather requests: use "personal_assistant" server, "get_weather" tool
- For task management: use "personal_assistant" server, "add_task" or "remove_task" tools
- For web search: use "personal_assistant" server, "search_web" tool
- For note search: use "knowledge_base" server, "search_notes" tool

User request: {user_input}

Respond with ONLY valid JSON:"""
        
        # Configure generation based on response mode
        generation_config = get_generation_config(response_mode)
        
        # Generate response
        if response_mode == "root_elicitation":
            response = await generate_with_root_elicitation(gemini_model, system_prompt, generation_config)
        else:
            response = gemini_model.generate_content(
                system_prompt,
                generation_config=generation_config
            )
            response = response.text
        
        # Parse and execute the response
        return await execute_gemini_response(response, mcp_manager)
    
    except Exception as e:
        logger.error(f"Error in interpret_and_execute: {e}")
        return f"❌ Error interpreting request: {str(e)}"

def create_mcp_context(tools: Dict, resources: Dict, prompts: Dict) -> str:
    """Create context string describing available MCP capabilities"""
    context = ""
    
    for server_name, server_tools in tools.items():
        if server_tools:
            context += f"\n{server_name} Tools:\n"
            for tool in server_tools:
                context += f"- {tool.get('name')}: {tool.get('description', 'No description')}\n"
    
    for server_name, server_resources in resources.items():
        if server_resources:
            context += f"\n{server_name} Resources:\n"
            for resource in server_resources:
                context += f"- {resource.get('uri')}: {resource.get('description', 'No description')}\n"
    
    for server_name, server_prompts in prompts.items():
        if server_prompts:
            context += f"\n{server_name} Prompts:\n"
            for prompt in server_prompts:
                context += f"- {prompt.get('name')}: {prompt.get('description', 'No description')}\n"
    
    return context

def get_generation_config(response_mode: str):
    """Get Gemini generation configuration based on response mode"""
    if response_mode == "deterministic":
        return genai.types.GenerationConfig(
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            max_output_tokens=2048
        )
    elif response_mode == "sampling":
        return genai.types.GenerationConfig(
            temperature=0.9,
            top_p=0.95,
            top_k=40,
            max_output_tokens=2048
        )
    else:  # root_elicitation
        return genai.types.GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=20,
            max_output_tokens=2048
        )

async def generate_with_root_elicitation(gemini_model, prompt: str, generation_config) -> str:
    """Generate multiple responses and pick the best one"""
    try:
        # Generate multiple responses
        responses = []
        for _ in range(3):
            response = gemini_model.generate_content(
                prompt,
                generation_config=generation_config
            )
            responses.append(response.text)
        
        # Use Gemini to pick the best response
        selection_prompt = f"""Given these three responses to a user query, select the best one based on accuracy, helpfulness, and clarity:

Response 1:
{responses[0]}

Response 2:
{responses[1]}

Response 3:
{responses[2]}

Respond with just the number (1, 2, or 3) of the best response."""
        
        selection = gemini_model.generate_content(
            selection_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        
        # Parse selection
        selection_text = selection.text.strip()
        if "1" in selection_text:
            return responses[0]
        elif "2" in selection_text:
            return responses[1]
        elif "3" in selection_text:
            return responses[2]
        else:
            return responses[0]  # Default to first response
    
    except Exception as e:
        logger.error(f"Error in root elicitation: {e}")
        # Fallback to single response
        response = gemini_model.generate_content(prompt, generation_config=generation_config)
        return response.text

async def execute_gemini_response(response_text: str, mcp_manager) -> str:
    """Parse and execute Gemini's response"""
    try:
        # Clean up the response text - remove markdown code blocks if present
        cleaned_response = response_text.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()
        
        # Try to parse as JSON
        try:
            response_data = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            # Log the parsing error and return the raw response
            logger.error(f"JSON parsing failed for response: {cleaned_response[:200]}... Error: {e}")
            return f"🤖 I generated a plan but couldn't execute it properly. Here's what I was trying to do:\n\n{response_text}"
        
        action = response_data.get("action")
        
        if action == "direct_response":
            return response_data.get("response", "No response provided")
        
        elif action == "mcp_call":
            operations = response_data.get("operations", [])
            explanation = response_data.get("explanation", "")
            
            result = f"🤖 {explanation}\n\n" if explanation else ""
            
            for operation in operations:
                op_type = operation.get("type")
                server = operation.get("server")
                name = operation.get("name")
                arguments = operation.get("arguments", {})
                
                try:
                    if op_type == "tool":
                        logger.info(f"Calling tool {name} on server {server} with args {arguments}")
                        tool_result = await mcp_manager.call_tool(server, name, arguments)
                        # tool_result is already a formatted string from the HTTP API
                        result += f"**{name} result:**\n{tool_result}\n\n"
                    
                    elif op_type == "resource":
                        logger.info(f"Reading resource {name} from server {server}")
                        resource_result = await mcp_manager.read_resource(server, name)
                        # resource_result is already a formatted string from the HTTP API
                        result += f"**{name} resource:**\n{resource_result}\n\n"
                    
                    elif op_type == "prompt":
                        logger.info(f"Getting prompt {name} from server {server} with args {arguments}")
                        prompt_result = await mcp_manager.get_prompt(server, name, arguments)
                        # prompt_result is already a formatted string from the HTTP API
                        result += f"**{name} prompt:**\n{prompt_result}\n\n"
                
                except Exception as e:
                    logger.error(f"Error executing {op_type} {name}: {e}")
                    result += f"❌ Error executing {op_type} {name}: {str(e)}\n\n"
            
            return result.strip()
        
        else:
            return f"🤖 I received an unknown action type: {action}. Raw response: {response_text}"
    
    except Exception as e:
        logger.error(f"Error executing Gemini response: {e}")
        return f"❌ Error executing response: {str(e)}\n\nRaw response: {response_text}"

def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title="MCP Learning System",
        page_icon="🤖",
        layout="wide"
    )
    
    st.title("🤖 MCP Learning System Chat")
    st.markdown("Chat with your Personal Assistant and Knowledge Base!")
    
    # Initialize session state
    initialize_session_state()
    
    # Initialize components
    if st.session_state.gemini_model is None:
        st.session_state.gemini_model = setup_gemini()
    
    if st.session_state.mcp_manager is None:
        with st.spinner("Connecting to MCP servers..."):
            st.session_state.mcp_manager = asyncio.run(setup_mcp_connections())
    
    # Check if initialization was successful
    if st.session_state.gemini_model is None or st.session_state.mcp_manager is None:
        st.error("Failed to initialize system components. Please check your configuration.")
        return
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        
        # Response mode selection
        response_mode = st.selectbox(
            "Response Mode",
            ["deterministic", "sampling", "root_elicitation"],
            index=0,
            help="Deterministic: Consistent responses (temp=0)\nSampling: Varied responses (temp=0.9)\nRoot Elicitation: Multiple responses, pick best"
        )
        st.session_state.response_mode = response_mode
        
        # Server status
        st.header("Server Status")
        if st.session_state.mcp_manager:
            connections = st.session_state.mcp_manager.get_all_connections()
            for server_name, connection in connections.items():
                status_color = "🟢" if connection.is_connected() else "🔴"
                st.write(f"{status_color} **{server_name.title()}**")
                st.write(f"   Status: {connection.connection_status}")
                st.write(f"   Transport: {connection.transport_type}")
                if connection.error_message:
                    st.write(f"   Error: {connection.error_message}")
        
        # Capabilities
        st.header("Available Capabilities")
        if st.button("Refresh Capabilities"):
            if st.session_state.mcp_manager:
                with st.spinner("Refreshing capabilities..."):
                    asyncio.run(st.session_state.mcp_manager.refresh_capabilities())
                st.success("Capabilities refreshed!")
        
        # Show capabilities summary
        if st.session_state.mcp_manager:
            capabilities = st.session_state.mcp_manager.get_all_capabilities()
            total_tools = sum(len(caps.get("tools", [])) for caps in capabilities.values())
            total_resources = sum(len(caps.get("resources", [])) for caps in capabilities.values())
            total_prompts = sum(len(caps.get("prompts", [])) for caps in capabilities.values())
            
            st.write(f"**Total Available:**")
            st.write(f"- Tools: {total_tools}")
            st.write(f"- Resources: {total_resources}")
            st.write(f"- Prompts: {total_prompts}")
        
        # Help section
        st.header("Commands")
        st.write("**Special Commands:**")
        st.write("- `/inspect` - Show all server capabilities")
        st.write("- Type naturally to interact with MCP servers")
        
        st.write("**Example Requests:**")
        st.write("- 'Add task: Buy groceries tomorrow'")
        st.write("- 'What's the weather in New York?'")
        st.write("- 'Search for Python best practices'")
        st.write("- 'Show me my tasks'")
    
    # Main chat interface
    display_chat_messages()
    
    # Chat input
    if prompt := st.chat_input("What can I help you with?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Process and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = asyncio.run(process_user_message(
                        prompt,
                        st.session_state.mcp_manager,
                        st.session_state.gemini_model,
                        st.session_state.response_mode
                    ))
                    st.markdown(response)
                except Exception as e:
                    error_msg = f"❌ Error processing request: {str(e)}"
                    st.markdown(error_msg)
                    response = error_msg
        
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()