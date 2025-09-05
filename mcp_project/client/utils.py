"""
Utility functions for MCP Learning System client.

Includes logging, retry logic, error handling, and helper functions.
"""

import asyncio
import logging
import time
import json
import os
from typing import Any, Callable, Optional, TypeVar, Dict, List
from functools import wraps
import random
import httpx
from pathlib import Path

# Type variable for generic functions
T = TypeVar('T')

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Set up logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('mcp_client.log')
        ]
    )
    return logging.getLogger(__name__)

class RetryConfig:
    """Configuration for retry logic"""
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

def retry_with_exponential_backoff(config: RetryConfig):
    """Decorator for retry logic with exponential backoff"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == config.max_attempts - 1:
                        break
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        config.base_delay * (config.exponential_base ** attempt),
                        config.max_delay
                    )
                    
                    # Add jitter to prevent thundering herd
                    if config.jitter:
                        delay *= (0.5 + random.random() * 0.5)
                    
                    logging.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    
                    await asyncio.sleep(delay)
            
            # If we get here, all attempts failed
            raise last_exception
        
        return wrapper
    return decorator

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                self._on_success()
                return result
                
            except self.expected_exception as e:
                self._on_failure()
                raise e
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _on_success(self):
        """Handle successful execution"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """Handle failed execution"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

def format_error_message(error: Exception, context: str = "") -> str:
    """Format error message for user display"""
    error_type = type(error).__name__
    error_message = str(error)
    
    if context:
        return f"Error in {context}: {error_type} - {error_message}"
    else:
        return f"{error_type}: {error_message}"

def sanitize_input(input_text: str, max_length: int = 1000) -> str:
    """Sanitize user input for safety"""
    if not isinstance(input_text, str):
        input_text = str(input_text)
    
    # Remove potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\r']
    sanitized = input_text
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '')
    
    # Limit length and strip whitespace
    sanitized = sanitized.strip()[:max_length]
    
    # Validate encoding (ensure it's valid UTF-8)
    try:
        sanitized.encode('utf-8')
    except UnicodeEncodeError:
        # If encoding fails, keep only ASCII characters
        sanitized = ''.join(char for char in sanitized if ord(char) < 128)
    
    return sanitized

def format_mcp_response(response: Dict[str, Any]) -> str:
    """Format MCP response for display in chat"""
    if not response:
        return "No response received"
    
    # Handle different response types
    if "content" in response:
        content = response["content"]
        if isinstance(content, list):
            # Handle list of content items
            formatted_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        formatted_parts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        formatted_parts.append(f"[Image: {item.get('source', 'unknown')}]")
                    else:
                        formatted_parts.append(str(item))
                else:
                    formatted_parts.append(str(item))
            return "\n".join(formatted_parts)
        else:
            return str(content)
    
    # Handle error responses
    if "error" in response:
        error = response["error"]
        if isinstance(error, dict):
            error_msg = error.get("message", "Unknown error")
            error_code = error.get("code", "")
            return f"Error {error_code}: {error_msg}" if error_code else f"Error: {error_msg}"
        else:
            return f"Error: {error}"
    
    # Handle tool results
    if "result" in response:
        result = response["result"]
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        else:
            return str(result)
    
    # Default formatting for other response types
    try:
        return json.dumps(response, indent=2)
    except (TypeError, ValueError):
        return str(response)

class RateLimiter:
    """Simple rate limiter implementation"""
    def __init__(self, max_calls: int, time_window: float):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    async def acquire(self):
        """Acquire permission to make a call"""
        now = time.time()
        
        # Remove old calls outside the time window
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.time_window]
        
        if len(self.calls) >= self.max_calls:
            # Calculate how long to wait
            oldest_call = min(self.calls)
            wait_time = self.time_window - (now - oldest_call)
            await asyncio.sleep(wait_time)
        
        self.calls.append(now)

# File I/O utilities
async def safe_read_json(file_path: str) -> Dict[str, Any]:
    """Safely read JSON file with error handling"""
    try:
        if not os.path.exists(file_path):
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return {}

async def safe_write_json(file_path: str, data: Dict[str, Any]) -> bool:
    """Safely write JSON file with error handling"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to temporary file first
        temp_path = file_path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic move
        os.replace(temp_path, file_path)
        return True
    except Exception as e:
        logger.error(f"Error writing {file_path}: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return False

async def safe_read_text(file_path: str) -> str:
    """Safely read text file with error handling"""
    try:
        if not os.path.exists(file_path):
            return ""
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return ""

# API client utilities
class APIClient:
    """Base API client with rate limiting and error handling"""
    
    def __init__(self, base_url: str, api_key: str = None, rate_limit: RateLimiter = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.rate_limiter = rate_limit or RateLimiter(max_calls=60, time_window=60.0)
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @retry_with_exponential_backoff(RetryConfig(max_attempts=3))
    async def get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make GET request with retry logic"""
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    
    @retry_with_exponential_backoff(RetryConfig(max_attempts=3))
    async def post(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make POST request with retry logic"""
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        response = await self.client.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()

# Validation utilities
def validate_email(email: str) -> bool:
    """Simple email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_url(url: str) -> bool:
    """Simple URL validation"""
    import re
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return re.match(pattern, url) is not None

def validate_date_string(date_str: str) -> bool:
    """Validate ISO date string format"""
    try:
        from datetime import datetime
        datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False

# Text processing utilities
def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract keywords from text using simple frequency analysis"""
    import re
    from collections import Counter
    
    # Common stop words to filter out
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
        'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
        'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
        'they', 'me', 'him', 'her', 'us', 'them'
    }
    
    # Extract words (alphanumeric only, minimum 3 characters)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out stop words and count frequency
    filtered_words = [word for word in words if word not in stop_words]
    word_counts = Counter(filtered_words)
    
    # Return most common words
    return [word for word, count in word_counts.most_common(max_keywords)]

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to specified length with suffix"""
    if len(text) <= max_length:
        return text
    
    # Try to break at word boundary
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.7:  # If we can break at a reasonable point
        truncated = truncated[:last_space]
    
    return truncated + suffix

# Async utilities
async def run_with_timeout(coro, timeout_seconds: float):
    """Run coroutine with timeout"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout_seconds} seconds")

async def gather_with_concurrency(tasks: List, max_concurrency: int = 5):
    """Run tasks with limited concurrency"""
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def run_task(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*[run_task(task) for task in tasks])

# Global logger instance
logger = setup_logging()