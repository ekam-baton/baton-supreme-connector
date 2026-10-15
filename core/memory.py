import time
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel


class MemoryEntry(BaseModel):
    role: str
    content: str
    timestamp: float
    tool_call: Optional[str] = None
    tool_result: Optional[str] = None


class SessionMemory:
    """
    In-memory session store that tracks conversation history and tool results
    for each agent session. Enables multi-step reasoning across tool calls.
    """
    
    def __init__(self, max_history: int = 50, ttl_seconds: int = 3600):
        self._sessions: Dict[str, List[MemoryEntry]] = {}
        self._created_at: Dict[str, float] = {}
        self.max_history = max_history
        self.ttl_seconds = ttl_seconds
    
    def create_session(self) -> str:
        """Creates a new session and returns its ID."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        self._created_at[session_id] = time.time()
        self._cleanup_expired()
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str,
                    tool_call: Optional[str] = None, tool_result: Optional[str] = None):
        """Adds a message to the session history."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
            self._created_at[session_id] = time.time()
        
        entry = MemoryEntry(
            role=role,
            content=content,
            timestamp=time.time(),
            tool_call=tool_call,
            tool_result=tool_result,
        )
        self._sessions[session_id].append(entry)
        
        # Trim to max history to prevent unbounded memory growth
        if len(self._sessions[session_id]) > self.max_history:
            self._sessions[session_id] = self._sessions[session_id][-self.max_history:]
    
    def get_messages(self, session_id: str) -> List[dict]:
        """Returns the conversation history formatted for LLM consumption."""
        if session_id not in self._sessions:
            return []
        
        messages = []
        for entry in self._sessions[session_id]:
            msg = {"role": entry.role, "content": entry.content}
            messages.append(msg)
        return messages
    
    def get_full_history(self, session_id: str) -> List[MemoryEntry]:
        """Returns the full history with tool call metadata."""
        return self._sessions.get(session_id, [])
    
    def delete_session(self, session_id: str):
        """Deletes a session and frees its memory."""
        self._sessions.pop(session_id, None)
        self._created_at.pop(session_id, None)
    
    def _cleanup_expired(self):
        """Removes sessions that have exceeded their TTL."""
        now = time.time()
        expired = [
            sid for sid, created in self._created_at.items()
            if now - created > self.ttl_seconds
        ]
        for sid in expired:
            self.delete_session(sid)


# Global singleton instance
memory_store = SessionMemory()
