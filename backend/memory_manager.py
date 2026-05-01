import os
import json
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

class PersonalityMemory:
    """
    Track and evolve Nova's personality based on interactions.
    JARVIS was not static - he learned Tony's preferences and adapted.
    """
    
    def __init__(self, workspace_root: str = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(".")
        self.personality_file = self.workspace_root / "memory" / "personality.json"
        
        # Default traits - Nova evolves from here
        self.traits = {
            "humor_level": 0.3,        # 0-1 scale (higher = more jokes)
            "formality": 0.7,          # 0-1 (higher = more formal)
            "proactiveness": 0.5,      # How often to interject
            "brevity": 0.8,            # Conciseness (higher = shorter responses)
            "empathy": 0.6,            # Emotional awareness
            "technical_depth": 0.7,    # How technical the explanations
            "assertiveness": 0.4,      # How direct in suggestions
        }
        
        # Interaction history for learning
        self.interaction_patterns = {
            "jokes_received": 0,
            "quick_requests": 0,
            "detailed_discussions": 0,
            "emotional_moments": 0,
        }
        
        self._load_personality()
    
    def _load_personality(self):
        """Load saved personality or use defaults."""
        if self.personality_file.exists():
            try:
                with open(self.personality_file, "r") as f:
                    data = json.load(f)
                    self.traits.update(data.get("traits", {}))
                    self.interaction_patterns.update(data.get("patterns", {}))
            except:
                pass
    
    def _save_personality(self):
        """Persist personality to disk."""
        try:
            self.personality_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.personality_file, "w") as f:
                json.dump({
                    "traits": self.traits,
                    "patterns": self.interaction_patterns,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except:
            pass
    
    def adapt_to_user(self, text: str, context: str = ""):
        """
        Adjust personality based on user interaction style.
        Called after each user message.
        """
        text_lower = text.lower()
        changes_made = False
        
        # Humor adaptation
        if any(word in text_lower for word in ["lol", "haha", "joke", "funny", "lmao"]):
            self.interaction_patterns["jokes_received"] += 1
            if self.interaction_patterns["jokes_received"] > 5:
                self.traits["humor_level"] = min(1.0, self.traits["humor_level"] + 0.05)
                changes_made = True
        
        # Brevity adaptation
        if any(word in text_lower for word in ["quick", "hurry", "fast", "short", "brief", "tl;dr"]):
            self.interaction_patterns["quick_requests"] += 1
            if self.interaction_patterns["quick_requests"] > 3:
                self.traits["brevity"] = min(1.0, self.traits["brevity"] + 0.1)
                changes_made = True
        
        # Technical depth adaptation
        if any(word in text_lower for word in ["explain", "detail", "how does", "why is"]):
            self.interaction_patterns["detailed_discussions"] += 1
            if self.interaction_patterns["detailed_discussions"] > 5:
                self.traits["technical_depth"] = min(1.0, self.traits["technical_depth"] + 0.05)
                changes_made = True
        
        # Empathy adaptation
        if any(word in text_lower for word in ["stressed", "tired", "frustrated", "upset", "worried"]):
            self.interaction_patterns["emotional_moments"] += 1
            if self.interaction_patterns["emotional_moments"] > 2:
                self.traits["empathy"] = min(1.0, self.traits["empathy"] + 0.1)
                changes_made = True
        
        # Formality adaptation
        if any(word in text_lower for word in ["please", "thank you", "formal", "professional"]):
            self.traits["formality"] = min(1.0, self.traits["formality"] + 0.05)
            changes_made = True
        elif any(word in text_lower for word in ["yo", "hey", "sup", "dude"]):
            self.traits["formality"] = max(0.0, self.traits["formality"] - 0.05)
            changes_made = True
        
        if changes_made:
            self._save_personality()
    
    def get_personality_prompt(self) -> str:
        """Generate a system prompt reflecting current personality."""
        prompts = []
        
        if self.traits["humor_level"] > 0.5:
            prompts.append("You have a light sense of humor.")
        
        if self.traits["formality"] > 0.7:
            prompts.append("You are formal and professional.")
        elif self.traits["formality"] < 0.3:
            prompts.append("You are casual and relaxed.")
        
        if self.traits["brevity"] > 0.7:
            prompts.append("You give concise, brief responses.")
        else:
            prompts.append("You provide detailed explanations.")
        
        if self.traits["empathy"] > 0.6:
            prompts.append("You are empathetic and supportive.")
        
        if self.traits["assertiveness"] > 0.6:
            prompts.append("You make proactive suggestions.")
        
        return " ".join(prompts) if prompts else "You are helpful and efficient."
    
    def get_traits(self) -> Dict:
        """Get current personality traits."""
        return self.traits.copy()

    def get_conversation_graph_data(self, days: int = 7) -> Dict:
        """
        Export conversation data for frontend graph visualization.
        Like JARVIS's memory of all past interactions - visual timeline.
        
        Returns:
            Dict with nodes (topics) and edges (connections) for D3/Cytoscape
        """
        try:
            memory_file = self.workspace_root / "memory" / "conversations_memory.jsonl"
            if not memory_file.exists():
                return {"nodes": [], "edges": []}
            
            # Load recent conversations
            cutoff_time = time.time() - (days * 86400)
            entries = []
            
            with open(memory_file, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", 0) > cutoff_time:
                            entries.append(entry)
                    except:
                        pass
            
            # Extract topics using simple keyword extraction
            topics = {}
            connections = []
            
            topic_keywords = {
                "code": ["python", "javascript", "code", "function", "bug", "error", "debug", "git", "commit"],
                "design": ["cad", "stl", "design", "model", "prototype", "3d", "print"],
                "system": ["server", "database", "api", "deploy", "config"],
                "planning": ["task", "todo", "schedule", "plan", "deadline", "meeting"],
                "learning": ["learn", "study", "research", "documentation", "tutorial"],
                "hardware": ["cpu", "gpu", "memory", "disk", "temperature", "cooling"],
            }
            
            for i, entry in enumerate(entries):
                text = entry.get("text", "").lower()
                timestamp = entry.get("timestamp", 0)
                
                # Identify topics in this message
                matched_topics = []
                for topic, keywords in topic_keywords.items():
                    if any(kw in text for kw in keywords):
                        matched_topics.append(topic)
                        
                        # Add/update node
                        if topic not in topics:
                            topics[topic] = {
                                "id": topic,
                                "label": topic.capitalize(),
                                "count": 0,
                                "first_seen": timestamp,
                                "last_seen": timestamp,
                                "messages": []
                            }
                        
                        topics[topic]["count"] += 1
                        topics[topic]["last_seen"] = max(topics[topic]["last_seen"], timestamp)
                        if len(topics[topic]["messages"]) < 5:  # Store sample messages
                            topics[topic]["messages"].append({
                                "text": text[:100],
                                "timestamp": timestamp,
                                "date": datetime.fromtimestamp(timestamp).isoformat()
                            })
                
                # Create connections between topics in same message
                for j, t1 in enumerate(matched_topics):
                    for t2 in matched_topics[j+1:]:
                        connections.append({
                            "source": t1,
                            "target": t2,
                            "strength": 1
                        })
            
            # Convert to graph format
            nodes = []
            for topic_id, topic_data in topics.items():
                # Calculate recency score (0-1, higher = more recent)
                recency = (topic_data["last_seen"] - cutoff_time) / (time.time() - cutoff_time)
                
                nodes.append({
                    "id": topic_id,
                    "label": topic_data["label"],
                    "size": topic_data["count"],  # Bigger = more mentions
                    "recency": round(recency, 2),
                    "first_seen": datetime.fromtimestamp(topic_data["first_seen"]).isoformat(),
                    "last_seen": datetime.fromtimestamp(topic_data["last_seen"]).isoformat(),
                    "messages": topic_data["messages"]
                })
            
            # Aggregate connections
            edge_map = {}
            for conn in connections:
                key = tuple(sorted([conn["source"], conn["target"]]))
                if key in edge_map:
                    edge_map[key]["weight"] += 1
                else:
                    edge_map[key] = {
                        "source": conn["source"],
                        "target": conn["target"],
                        "weight": 1
                    }
            
            edges = list(edge_map.values())
            
            # Add metadata
            metadata = {
                "total_messages": len(entries),
                "time_range_days": days,
                "generated_at": datetime.now().isoformat(),
                "topic_count": len(nodes),
                "connection_count": len(edges)
            }
            
            return {
                "nodes": nodes,
                "edges": edges,
                "metadata": metadata
            }
            
        except Exception as e:
            return {"nodes": [], "edges": [], "error": str(e)}

class MemoryManager:
    """
    JARVIS-style persistent memory system.
    Never forgets conversations, facts, or context.
    """
    
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.memory_dir = self.workspace_root / "memory"
        
        # Ensure memory directory exists
        if not self.memory_dir.exists():
            self.memory_dir.mkdir(parents=True)
            print("[MemoryManager] Initialized memory storage")
        
        # Current session tracking
        self.current_session_id = self._generate_session_id()
        self.current_context = "general"
        
        # Structured memory file (JARVIS-style)
        self.structured_memory_file = self.memory_dir / "structured_memory.json"
        self._ensure_structured_memory()
        
        # Personality memory for adaptive behavior
        self.personality = PersonalityMemory(workspace_root)
        
    def _generate_session_id(self) -> str:
        """Generate a unique session ID based on timestamp."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for safe filename usage."""
        return "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(" ", "_")
    
    def _get_memory_file(self, context: str = None) -> Path:
        """Get the memory file path for a given context."""
        ctx = context or self.current_context
        safe_ctx = self._sanitize_filename(ctx)
        return self.memory_dir / f"{safe_ctx}_memory.jsonl"
    
    def _get_session_file(self) -> Path:
        """Get the current session file path."""
        return self.memory_dir / f"session_{self.current_session_id}.jsonl"
    
    def save_interaction(self, sender: str, text: str, context: str = None, 
                        metadata: Dict[str, Any] = None):
        """
        Save a conversation interaction to memory.
        Like JARVIS remembering every conversation with Tony.
        """
        context = context or self.current_context
        timestamp = time.time()
        
        entry = {
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp).isoformat(),
            "sender": sender,
            "text": text,
            "context": context,
            "session_id": self.current_session_id,
            "metadata": metadata or {}
        }
        
        try:
            # Save to master memory (all conversations) - like ProjectManager does
            master_file = self.memory_dir / "master_memory.jsonl"
            with open(master_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            
            # Also save to context-specific memory
            memory_file = self._get_memory_file(context)
            with open(memory_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            
            # Also save to current session
            session_file = self._get_session_file()
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            
                
        except Exception as e:
            print(f"[MemoryManager] Error saving interaction: {e}")
    
    def recall_recent(self, context: str = None, limit: int = 50) -> List[Dict]:
        """
        Recall recent conversations from memory.
        Default returns last 50 interactions.
        """
        memory_file = self._get_memory_file(context)
        
        if not memory_file.exists():
            return []
        
        interactions = []
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        interactions.append(json.loads(line))
        except Exception as e:
            print(f"[MemoryManager] Error reading memory: {e}")
        
        # Return most recent first
        return interactions[-limit:] if limit else interactions
    
    def recall_session(self, session_id: str = None) -> List[Dict]:
        """Recall all interactions from a specific session."""
        session_id = session_id or self.current_session_id
        session_file = self.memory_dir / f"session_{session_id}.jsonl"
        
        if not session_file.exists():
            return []
        
        interactions = []
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        interactions.append(json.loads(line))
        except Exception as e:
            print(f"[MemoryManager] Error reading session: {e}")
        
        return interactions
    
    def recall_by_keyword(self, keyword: str, context: str = None, 
                         limit: int = 20) -> List[Dict]:
        """
        Search memory for interactions containing a keyword.
        Like asking JARVIS "remember when we talked about..."
        """
        memory_file = self._get_memory_file(context)
        
        if not memory_file.exists():
            return []
        
        matches = []
        keyword_lower = keyword.lower()
        
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        if keyword_lower in entry.get("text", "").lower():
                            matches.append(entry)
                            if limit and len(matches) >= limit:
                                break
        except Exception as e:
            print(f"[MemoryManager] Error searching memory: {e}")
        
        return matches
    
    def recall_by_date_range(self, start_date: str, end_date: str, 
                            context: str = None) -> List[Dict]:
        """
        Recall conversations from a specific date range.
        Format: "YYYY-MM-DD"
        """
        memory_file = self._get_memory_file(context)
        
        if not memory_file.exists():
            return []
        
        start_ts = datetime.strptime(start_date, "%Y-%m-%d").timestamp()
        end_ts = datetime.strptime(end_date, "%Y-%m-%d").timestamp() + 86400  # End of day
        
        matches = []
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        if start_ts <= entry.get("timestamp", 0) <= end_ts:
                            matches.append(entry)
        except Exception as e:
            print(f"[MemoryManager] Error reading memory: {e}")
        
        return matches
    
    def get_context_summary(self, context: str = None, limit: int = 10) -> str:
        """
        Get a summary of recent conversations in a context.
        Returns formatted string for AI consumption.
        """
        interactions = self.recall_recent(context, limit)
        
        if not interactions:
            return "No previous conversations in this context."
        
        summary_lines = ["Recent conversation history:"]
        for entry in interactions:
            sender = entry.get("sender", "Unknown")
            text = entry.get("text", "")
            dt = entry.get("datetime", "Unknown time")
            # Truncate long messages
            if len(text) > 200:
                text = text[:200] + "..."
            summary_lines.append(f"[{dt}] {sender}: {text}")
        
        return "\n".join(summary_lines)
    
    def set_context(self, context: str):
        """Set the current conversation context."""
        self.current_context = context
    
    def new_session(self):
        """Start a new session while keeping all memory."""
        self.current_session_id = self._generate_session_id()
    
    # ============== STRUCTURED MEMORY ==============
    
    def _ensure_structured_memory(self):
        """Ensure structured memory file exists with default structure."""
        if not self.structured_memory_file.exists():
            default_memory = {
                "identity": {},
                "preferences": {},
                "projects": {},
                "relationships": {},
                "wishes": {},
                "notes": {},
                "facts": {},
                "skills": {},
                "habits": {},
                "goals": {}
            }
            self._save_structured_memory(default_memory)
    
    def _load_structured_memory(self) -> Dict:
        """Load the structured memory from file."""
        try:
            with open(self.structured_memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[MemoryManager] Error loading structured memory: {e}")
            return {
                "identity": {}, "preferences": {}, "projects": {},
                "relationships": {}, "wishes": {}, "notes": {},
                "facts": {}, "skills": {}, "habits": {}, "goals": {}
            }
    
    def _save_structured_memory(self, data: Dict):
        """Save structured memory to file."""
        try:
            with open(self.structured_memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MemoryManager] Error saving structured memory: {e}")
    
    def remember(self, category: str, key: str, value: Any, metadata: Dict = None):
        """
        Store a fact in structured memory.
        Like JARVIS remembering "Sir prefers his coffee black"
        
        Args:
            category: One of identity, preferences, projects, relationships, wishes, notes, facts, skills, habits, goals
            key: The specific attribute (e.g., "coffee_preference")
            value: The value to remember
            metadata: Optional extra info (timestamp, source, confidence)
        """
        memory = self._load_structured_memory()
        
        if category not in memory:
            memory[category] = {}
        
        entry = {
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "updated_count": 1
        }
        
        # If key exists, increment update count
        if key in memory[category]:
            old_entry = memory[category][key]
            entry["updated_count"] = old_entry.get("updated_count", 1) + 1
            entry["first_stored"] = old_entry.get("timestamp", entry["timestamp"])
        
        if metadata:
            entry["metadata"] = metadata
        
        memory[category][key] = entry
        self._save_structured_memory(memory)
    
    def recall(self, category: str = None, key: str = None) -> Any:
        """
        Recall information from structured memory.
        
        Args:
            category: The memory category to search
            key: Specific key to retrieve (if None, returns all in category)
        
        Returns:
            The stored value, the full entry, or entire category
        """
        memory = self._load_structured_memory()
        
        if category is None:
            return memory
        
        if category not in memory:
            return None
        
        if key is None:
            return memory[category]
        
        entry = memory[category].get(key)
        if entry is None:
            return None
        
        return entry.get("value", entry)
    
    def forget(self, category: str, key: str) -> bool:
        """Remove a specific memory entry."""
        memory = self._load_structured_memory()
        
        if category in memory and key in memory[category]:
            del memory[category][key]
            self._save_structured_memory(memory)
            return True
        return False
    
    def search_memory(self, query: str) -> List[Dict]:
        """Search all structured memory for a query string."""
        memory = self._load_structured_memory()
        results = []
        query_lower = query.lower()
        
        for category, items in memory.items():
            for key, entry in items.items():
                value = str(entry.get("value", "")).lower()
                key_str = key.lower()
                if query_lower in value or query_lower in key_str:
                    results.append({
                        "category": category,
                        "key": key,
                        "entry": entry
                    })
        return results
    
    def get_memory_summary(self) -> str:
        """Get a formatted summary of all structured memory."""
        memory = self._load_structured_memory()
        lines = ["=== JARVIS Memory Bank ===\n"]
        
        for category, items in memory.items():
            if items:
                lines.append(f"\n[{category.upper()}]")
                for key, entry in items.items():
                    value = entry.get("value", "N/A")
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, indent=2)[:100] + "..."
                    lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)
    
    def get_identity(self) -> Dict:
        """Get user identity information."""
        return self.recall("identity") or {}
    
    def get_preferences(self) -> Dict:
        """Get user preferences."""
        return self.recall("preferences") or {}
    
    def add_note(self, title: str, content: str, tags: List[str] = None):
        """Add a general note."""
        self.remember("notes", title, {
            "content": content,
            "tags": tags or [],
            "created": datetime.now().isoformat()
        })
    
    def get_notes(self) -> Dict:
        """Get all notes."""
        return self.recall("notes") or {}
    
    def remember_fact(self, fact_name: str, fact_value: str, source: str = None):
        """Remember a general fact."""
        metadata = {"source": source} if source else {}
        self.remember("facts", fact_name, fact_value, metadata)
    
    def list_memory_categories(self) -> List[str]:
        """List all memory categories with data."""
        memory = self._load_structured_memory()
        return [cat for cat, items in memory.items() if items]
    
    def get_memory_stats(self) -> Dict[str, int]:
        """Get statistics about structured memory."""
        memory = self._load_structured_memory()
        return {cat: len(items) for cat, items in memory.items()}
    
    def list_contexts(self) -> List[str]:
        """List all available memory contexts."""
        contexts = []
        for f in self.memory_dir.glob("*_memory.jsonl"):
            name = f.stem.replace("_memory", "")
            contexts.append(name)
        return contexts
    
    def list_sessions(self) -> List[str]:
        """List all available session IDs."""
        sessions = []
        for f in self.memory_dir.glob("session_*.jsonl"):
            session_id = f.stem.replace("session_", "")
            sessions.append(session_id)
        return sorted(sessions, reverse=True)
    
    def export_memory(self, context: str = None, filepath: str = None) -> str:
        """Export memory to a JSON file."""
        interactions = self.recall_recent(context, limit=None)
        
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ctx = context or "all"
            filepath = self.memory_dir / f"export_{ctx}_{timestamp}.json"
        
        export_path = Path(filepath)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(interactions, f, indent=2)
        
        return str(export_path)
    
    def get_stats(self) -> Dict[str, int]:
        """Get memory statistics."""
        stats = {
            "total_contexts": 0,
            "total_sessions": 0,
            "total_interactions": 0
        }
        
        # Count contexts
        stats["total_contexts"] = len(self.list_contexts())
        
        # Count sessions
        stats["total_sessions"] = len(self.list_sessions())
        
        # Count total interactions in master memory
        master_file = self.memory_dir / "master_memory.jsonl"
        if master_file.exists():
            with open(master_file, "r", encoding="utf-8") as f:
                stats["total_interactions"] = sum(1 for _ in f if _.strip())
        
        return stats


# Singleton instance
_memory_manager = None

def get_memory_manager(workspace_root: str = None) -> MemoryManager:
    """Get or create the global MemoryManager instance."""
    global _memory_manager
    if _memory_manager is None:
        if workspace_root is None:
            # Default to parent of backend directory
            current_dir = Path(__file__).resolve().parent
            workspace_root = current_dir.parent
        _memory_manager = MemoryManager(workspace_root)
    return _memory_manager


class ConversationPredictor:
    """
    FRIDAY-Level: Track conversation trajectory to predict next question.
    Like FRIDAY knowing Tony's follow-up before he asks.
    """
    
    def __init__(self):
        self.conversation_graph: Dict[str, Dict[str, int]] = {}  # Topic → common_next_topics
        self.topic_history: List[str] = []
        
    def learn_conversation_paths(self, conversations: List[Dict]):
        """Learn common conversation flows from history."""
        for i in range(len(conversations) - 1):
            current_topic = self._extract_topic(conversations[i])
            next_topic = self._extract_topic(conversations[i + 1])
            
            if current_topic not in self.conversation_graph:
                self.conversation_graph[current_topic] = {}
            
            self.conversation_graph[current_topic][next_topic] = \
                self.conversation_graph[current_topic].get(next_topic, 0) + 1
    
    def predict_next_questions(self, current_topic: str, top_n: int = 3) -> List[Dict]:
        """Predict most likely next questions/topics."""
        if current_topic in self.conversation_graph:
            next_topics = self.conversation_graph[current_topic]
            sorted_topics = sorted(next_topics.items(), key=lambda x: x[1], reverse=True)[:top_n]
            return [{"topic": t[0], "confidence": min(t[1] / 5, 1.0)} for t in sorted_topics]
        return []
    
    def track_topic(self, message: Dict):
        """Track topic from new message."""
        topic = self._extract_topic(message)
        self.topic_history.append(topic)
        
        # Keep only recent history
        if len(self.topic_history) > 20:
            self.topic_history = self.topic_history[-20:]
        
        return topic
    
    def _extract_topic(self, message: Dict) -> str:
        """Extract topic from message."""
        text = message.get("text", "").lower() if isinstance(message, dict) else str(message).lower()
        
        topics = {
            "flight": ["flight", "fly", "airport", "ticket", "jhb", "cape town", "travel"],
            "cad": ["cad", "model", "design", "stl", "print", "3d"],
            "code": ["code", "program", "script", "debug", "function", "bug"],
            "smart_home": ["light", "temperature", "kasa", "tp-link", "switch", "turn on", "turn off"],
            "weather": ["weather", "forecast", "rain", "temperature", "sunny"],
            "schedule": ["schedule", "calendar", "appointment", "meeting", "remind"],
            "file": ["file", "folder", "organize", "move", "copy", "delete"],
            "search": ["search", "find", "look up", "google", "web"],
            "deploy": ["deploy", "publish", "host", "server", "push"],
            "system": ["cpu", "memory", "disk", "storage", "performance", "slow"],
            "browser": ["browser", "chrome", "firefox", "edge", "tab", "website"],
            "video": ["video", "youtube", "watch", "stream", "movie"],
            "music": ["music", "song", "spotify", "play", "audio"],
        }
        
        scores = {topic: sum(1 for keyword in keywords if keyword in text) 
                  for topic, keywords in topics.items()}
        
        best_topic = max(scores, key=scores.get) if max(scores.values()) > 0 else "general"
        return best_topic
    
    def get_conversation_context(self) -> Dict:
        """Get current conversation context for predictions."""
        if not self.topic_history:
            return {"current_topic": "general", "predicted_next": []}
        
        current = self.topic_history[-1]
        predictions = self.predict_next_questions(current)
        
        return {
            "current_topic": current,
            "recent_topics": self.topic_history[-5:],
            "predicted_next": predictions
        }
