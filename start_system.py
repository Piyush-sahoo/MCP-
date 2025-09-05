#!/usr/bin/env python3
"""
MCP Learning System Startup Script

This script starts all components of the MCP Learning System:
1. Personal Assistant Server (port 8001)
2. Knowledge Base Server (port 8002)
3. Streamlit Web Interface (port 8501)

Usage:
    python start_system.py

Requirements:
    - All dependencies installed (pip install -r requirements.txt)
    - API keys configured in .env file
    - Virtual environment activated (recommended)
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def check_requirements():
    """Check if basic requirements are met"""
    print("🔍 Checking system requirements...")
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("❌ .env file not found. Please copy .env.template to .env and configure your API keys.")
        return False
    
    # Check if virtual environment is activated
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Virtual environment not detected. It's recommended to activate your virtual environment first.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return False
    
    print("✅ Requirements check passed!")
    return True

def start_server(name, command, port):
    """Start a server process"""
    print(f"🚀 Starting {name} on port {port}...")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(2)  # Give the server time to start
        
        # Check if process is still running
        if process.poll() is None:
            print(f"✅ {name} started successfully (PID: {process.pid})")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"❌ {name} failed to start:")
            print(f"   stdout: {stdout}")
            print(f"   stderr: {stderr}")
            return None
    except Exception as e:
        print(f"❌ Error starting {name}: {e}")
        return None

def main():
    """Main startup function"""
    print("🤖 MCP Learning System Startup")
    print("=" * 50)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    processes = []
    
    try:
        # Start Personal Assistant Server
        pa_process = start_server(
            "Personal Assistant Server",
            f'"{sys.executable}" -m servers.personal_assistant.http_server',
            8001
        )
        if pa_process:
            processes.append(("Personal Assistant", pa_process))
        
        # Start Knowledge Base Server
        kb_process = start_server(
            "Knowledge Base Server",
            f'"{sys.executable}" -m servers.knowledge_base.http_server',
            8002
        )
        if kb_process:
            processes.append(("Knowledge Base", kb_process))
        
        # Start Streamlit Web Interface
        streamlit_process = start_server(
            "Streamlit Web Interface",
            f'"{sys.executable}" -m streamlit run client/streamlit_chat.py --server.port 8501',
            8501
        )
        if streamlit_process:
            processes.append(("Streamlit", streamlit_process))
        
        if not processes:
            print("❌ No services started successfully. Please check your configuration.")
            sys.exit(1)
        
        print("\n🎉 MCP Learning System is now running!")
        print("=" * 50)
        print("📱 Web Interface: http://localhost:8501")
        print("🔧 Personal Assistant API: http://localhost:8001")
        print("🧠 Knowledge Base API: http://localhost:8002")
        print("\n💡 Tips:")
        print("   - Try asking: 'What's the weather in London?'")
        print("   - Try asking: 'Search for latest AI news'")
        print("   - Try asking: 'Tell me about the knowledge base'")
        print("   - Use /inspect command to see all available tools")
        print("\n⏹️  Press Ctrl+C to stop all services")
        
        # Keep the script running and monitor processes
        while True:
            time.sleep(5)
            # Check if any process has died
            for name, process in processes:
                if process.poll() is not None:
                    print(f"⚠️  {name} process has stopped unexpectedly")
    
    except KeyboardInterrupt:
        print("\n🛑 Shutting down MCP Learning System...")
        
        # Terminate all processes
        for name, process in processes:
            try:
                print(f"   Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"   Force killing {name}...")
                process.kill()
            except Exception as e:
                print(f"   Error stopping {name}: {e}")
        
        print("✅ All services stopped. Goodbye!")
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()