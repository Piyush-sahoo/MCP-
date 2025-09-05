# Python Async Programming Guide

## Introduction

Asynchronous programming in Python allows you to write concurrent code that can handle multiple operations without blocking the main thread. This is particularly useful for I/O-bound operations like network requests, file operations, and database queries.

## Key Concepts

### Event Loop
The event loop is the core of every asyncio application. It runs asynchronous tasks and callbacks, performs network I/O operations, and runs subprocesses.

```python
import asyncio

async def main():
    print("Hello")
    await asyncio.sleep(1)
    print("World")

# Run the event loop
asyncio.run(main())
```

### Coroutines
Coroutines are functions defined with `async def` that can be paused and resumed. They are the building blocks of asyncio applications.

```python
async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()
```

### Tasks and Futures
Tasks are used to schedule coroutines concurrently. They wrap coroutines and allow them to run in the background.

```python
async def main():
    # Create tasks
    task1 = asyncio.create_task(fetch_data("http://example.com"))
    task2 = asyncio.create_task(fetch_data("http://google.com"))
    
    # Wait for both tasks to complete
    result1, result2 = await asyncio.gather(task1, task2)
```

## Common Patterns

### Concurrent Execution
Use `asyncio.gather()` to run multiple coroutines concurrently:

```python
async def process_urls(urls):
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results
```

### Limiting Concurrency
Use `asyncio.Semaphore` to limit the number of concurrent operations:

```python
async def limited_fetch(semaphore, url):
    async with semaphore:
        return await fetch_data(url)

async def main():
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
    tasks = [limited_fetch(semaphore, url) for url in urls]
    results = await asyncio.gather(*tasks)
```

### Error Handling
Always handle exceptions in async code:

```python
async def safe_fetch(url):
    try:
        return await fetch_data(url)
    except aiohttp.ClientError as e:
        print(f"Error fetching {url}: {e}")
        return None
```

## Best Practices

1. **Use async/await consistently** - Don't mix blocking and non-blocking code
2. **Handle exceptions properly** - Use try/except blocks around await calls
3. **Limit concurrency** - Use semaphores to prevent overwhelming servers
4. **Use connection pooling** - Reuse HTTP connections when possible
5. **Profile your code** - Use tools like `asyncio.get_event_loop().set_debug(True)`

## Common Pitfalls

- **Blocking the event loop** - Never use blocking I/O in async functions
- **Not awaiting coroutines** - Always await async function calls
- **Creating too many tasks** - Limit concurrency to prevent resource exhaustion
- **Mixing sync and async code** - Use `asyncio.run_in_executor()` for CPU-bound tasks

## Libraries and Tools

- **aiohttp** - Async HTTP client/server
- **aiofiles** - Async file operations
- **asyncpg** - Async PostgreSQL driver
- **motor** - Async MongoDB driver
- **uvloop** - Fast event loop implementation

Tags: python, async, asyncio, concurrency, programming, performance