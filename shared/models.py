"""
Shared data models for MCP servers
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import json
import hashlib
from pathlib import Path


class ConnectionStatus(Enum):
    """Connection status for MCP servers"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPConnection:
    """MCP server connection information"""
    name: str
    host: str
    port: int
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    error_message: Optional[str] = None
    tools: List[Dict[str, Any]] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    prompts: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert connection to dictionary"""
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "error_message": self.error_message,
            "tools": self.tools,
            "resources": self.resources,
            "prompts": self.prompts
        }


@dataclass
class Task:
    """Task model for personal assistant"""
    id: str
    title: str
    description: str = ""
    completed: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    due_date: Optional[str] = None
    priority: str = "medium"  # low, medium, high
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "due_date": self.due_date,
            "priority": self.priority,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create task from dictionary"""
        return cls(**data)


@dataclass
class Note:
    """Note model for knowledge base"""
    id: str
    title: str
    content: str
    file_path: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags: List[str] = field(default_factory=list)
    word_count: int = 0
    
    def __post_init__(self):
        """Calculate word count after initialization"""
        if self.word_count == 0:
            self.word_count = len(self.content.split())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert note to dictionary"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "file_path": self.file_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "word_count": self.word_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Note":
        """Create note from dictionary"""
        return cls(**data)
    
    @classmethod
    def from_file(cls, file_path: str, content: str, title: Optional[str] = None) -> "Note":
        """Create note from file content"""
        # Generate ID from file path
        note_id = hashlib.md5(file_path.encode()).hexdigest()[:8]
        
        # Extract title if not provided
        if not title:
            title = Path(file_path).stem.replace('_', ' ').replace('-', ' ').title()
        
        # Extract tags from content (simple implementation)
        tags = []
        content_lower = content.lower()
        
        # Common programming/tech keywords as tags
        tech_keywords = ['python', 'javascript', 'api', 'docker', 'kubernetes', 
                        'machine learning', 'ai', 'database', 'sql', 'nosql',
                        'react', 'vue', 'angular', 'nodejs', 'async', 'sync']
        
        for keyword in tech_keywords:
            if keyword in content_lower:
                tags.append(keyword)
        
        return cls(
            id=note_id,
            title=title,
            content=content,
            file_path=file_path,
            tags=tags[:5]  # Limit to 5 tags
        )
    
    def search_relevance(self, keyword: str) -> float:
        """Calculate relevance score for search keyword"""
        keyword_lower = keyword.lower()
        score = 0.0
        
        # Title match (highest weight)
        if keyword_lower in self.title.lower():
            score += 10.0
            # Exact match bonus
            if keyword_lower == self.title.lower():
                score += 5.0
        
        # Content matches
        content_lower = self.content.lower()
        occurrences = content_lower.count(keyword_lower)
        score += min(occurrences * 0.5, 5.0)  # Cap at 5 points for content
        
        # Tag match
        for tag in self.tags:
            if keyword_lower in tag.lower():
                score += 2.0
        
        # File name match
        if keyword_lower in Path(self.file_path).stem.lower():
            score += 3.0
        
        return score