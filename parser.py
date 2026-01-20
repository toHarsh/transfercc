"""
ChatGPT Export Parser
Parses the conversations.json from ChatGPT data export
"""

import json
import os
from datetime import datetime
from dateutil import parser as date_parser
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Message:
    """Represents a single message in a conversation"""
    id: str
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: Optional[datetime] = None
    model: Optional[str] = None
    
    def to_markdown(self) -> str:
        role_emoji = {"user": "👤", "assistant": "🤖", "system": "⚙️", "tool": "🔧"}
        emoji = role_emoji.get(self.role, "💬")
        header = f"### {emoji} {self.role.title()}"
        if self.timestamp:
            header += f" – {self.timestamp.strftime('%b %d, %Y %I:%M %p')}"
        return f"{header}\n\n{self.content}\n"


@dataclass
class Conversation:
    """Represents a ChatGPT conversation"""
    id: str
    title: str
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    messages: List[Message] = field(default_factory=list)
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    model: Optional[str] = None
    
    def to_markdown(self) -> str:
        lines = [f"# {self.title}\n"]
        
        if self.project_name:
            lines.append(f"**Project:** {self.project_name}\n")
        if self.create_time:
            lines.append(f"**Created:** {self.create_time.strftime('%B %d, %Y')}\n")
        if self.update_time:
            lines.append(f"**Last Updated:** {self.update_time.strftime('%B %d, %Y')}\n")
        if self.model:
            lines.append(f"**Model:** {self.model}\n")
        
        lines.append("\n---\n")
        
        for msg in self.messages:
            lines.append(msg.to_markdown())
        
        return "\n".join(lines)
    
    def get_preview(self, max_length: int = 200) -> str:
        """Get a preview of the conversation content"""
        for msg in self.messages:
            if msg.role == 'user' and msg.content:
                content = msg.content.strip()
                if len(content) > max_length:
                    return content[:max_length] + "..."
                return content
        return "No preview available"
    
    def word_count(self) -> int:
        return sum(len(msg.content.split()) for msg in self.messages)


@dataclass
class Project:
    """Represents a ChatGPT project (folder)"""
    id: str
    name: str
    conversations: List[Conversation] = field(default_factory=list)
    
    @property
    def message_count(self) -> int:
        """Total messages across all conversations in this project"""
        return sum(len(c.messages) for c in self.conversations)
    
    @property
    def word_count(self) -> int:
        """Total words across all conversations in this project"""
        return sum(c.word_count() for c in self.conversations)


class ChatGPTParser:
    """Parser for ChatGPT data export"""
    
    def __init__(self, export_path: str = None):
        self.export_path = export_path
        self.conversations: List[Conversation] = []
        self.projects: Dict[str, Project] = {}
        self.unassigned_conversations: List[Conversation] = []
        
    def parse(self) -> None:
        """Parse the ChatGPT export from file path"""
        if not self.export_path:
            raise ValueError("No export path provided")
            
        conversations_file = os.path.join(self.export_path, "conversations.json")
        
        if not os.path.exists(conversations_file):
            raise FileNotFoundError(f"conversations.json not found in {self.export_path}")
        
        with open(conversations_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._parse_data(data)
    
    def parse_from_json(self, data: List[Dict[str, Any]]) -> None:
        """Parse directly from JSON data (list of conversations)"""
        if not isinstance(data, list):
            raise TypeError(f"Expected list of conversations, got {type(data).__name__}")
        if len(data) == 0:
            raise ValueError("Data list is empty")
        self._parse_data(data)
    
    def _parse_data(self, data: List[Dict[str, Any]]) -> None:
        """Internal method to parse conversation data"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Starting to parse {len(data)} conversation entries")
        
        parse_errors = []
        for idx, conv_data in enumerate(data):
            try:
                if not isinstance(conv_data, dict):
                    logger.warning(f"Conversation {idx} is not a dict (got {type(conv_data).__name__}), skipping")
                    parse_errors.append(f"Entry {idx}: not a dict")
                    continue
                
                conversation = self._parse_conversation(conv_data)
                
                # Only add conversations that have messages
                if len(conversation.messages) > 0:
                    self.conversations.append(conversation)
                    
                    if conversation.project_id and conversation.project_name:
                        if conversation.project_id not in self.projects:
                            self.projects[conversation.project_id] = Project(
                                id=conversation.project_id,
                                name=conversation.project_name
                            )
                        self.projects[conversation.project_id].conversations.append(conversation)
                    else:
                        self.unassigned_conversations.append(conversation)
                else:
                    logger.warning(f"Conversation {idx} ({conversation.id}) has no messages, skipping")
            except Exception as e:
                logger.exception(f"Error parsing conversation {idx}: {e}")
                parse_errors.append(f"Entry {idx}: {str(e)}")
                continue
        
        if parse_errors:
            logger.warning(f"Encountered {len(parse_errors)} parsing errors (first 5): {parse_errors[:5]}")
        
        if len(self.conversations) == 0 and len(data) > 0:
            error_summary = f"Failed to parse any conversations from {len(data)} entries"
            if parse_errors:
                error_summary += f". Sample errors: {', '.join(parse_errors[:3])}"
            raise ValueError(error_summary)
        
        logger.info(f"Successfully parsed {len(self.conversations)} conversations with messages")
        
        # Sort conversations by date
        self.conversations.sort(key=lambda c: c.update_time or datetime.min, reverse=True)
        self.unassigned_conversations.sort(key=lambda c: c.update_time or datetime.min, reverse=True)
        for project in self.projects.values():
            project.conversations.sort(key=lambda c: c.update_time or datetime.min, reverse=True)
    
    def _parse_conversation(self, data: Dict[str, Any]) -> Conversation:
        """Parse a single conversation from the export data"""
        # Try multiple possible keys for conversation ID
        conv_id = (data.get("id") or 
                  data.get("conversation_id") or 
                  data.get("uuid") or
                  (data.get("mapping", {}).get(list(data.get("mapping", {}).keys())[0], {}).get("message", {}).get("id") if data.get("mapping") else None) or
                  f"conv_{hash(str(data))}")
        
        # Ensure we have a string ID
        if not isinstance(conv_id, str):
            conv_id = str(conv_id)
        
        title = data.get("title", "Untitled Conversation")
        
        # Parse timestamps
        create_time = None
        update_time = None
        if data.get("create_time"):
            try:
                create_time = datetime.fromtimestamp(data["create_time"])
            except (ValueError, TypeError, OSError):
                pass
        if data.get("update_time"):
            try:
                update_time = datetime.fromtimestamp(data["update_time"])
            except (ValueError, TypeError, OSError):
                pass
        
        # Parse project info (ChatGPT calls them "gizmo" or folder)
        project_id = None
        project_name = None
        
        # Check various possible locations for project/folder info
        if "folder_id" in data:
            project_id = data["folder_id"]
            project_name = data.get("folder_name", f"Project {project_id[:8]}")
        elif "gizmo_id" in data and data.get("gizmo_id"):
            project_id = data["gizmo_id"]
            project_name = data.get("gizmo_name", f"GPT {project_id[:8]}")
        elif "conversation_template_id" in data:
            project_id = data.get("conversation_template_id")
            project_name = data.get("conversation_template_name", "Custom GPT")
        
        # Parse messages
        messages = self._parse_messages(data)
        
        # Get model info
        model = data.get("default_model_slug", None)
        
        return Conversation(
            id=conv_id,
            title=title,
            create_time=create_time,
            update_time=update_time,
            messages=messages,
            project_id=project_id,
            project_name=project_name,
            model=model
        )
    
    def _parse_messages(self, data: Dict[str, Any]) -> List[Message]:
        """Parse messages from a conversation"""
        messages = []
        
        # ChatGPT export uses a mapping structure
        mapping = data.get("mapping", {})
        
        if not mapping:
            # Try alternative structure - maybe messages are directly in the data
            if "messages" in data and isinstance(data["messages"], list):
                # Handle direct messages array
                for msg_data in data["messages"]:
                    if isinstance(msg_data, dict):
                        role = msg_data.get("role", msg_data.get("author", {}).get("role", "unknown"))
                        content = msg_data.get("content", "")
                        if isinstance(content, dict):
                            content = content.get("text", content.get("parts", [""])[0] if content.get("parts") else "")
                        
                        if content and content.strip():
                            messages.append(Message(
                                id=msg_data.get("id", f"msg_{len(messages)}"),
                                role=role,
                                content=str(content),
                                timestamp=None,
                                model=msg_data.get("model")
                            ))
                return messages
            return messages
        
        # Find message order by following parent-child relationships
        message_nodes = []
        for node_id, node in mapping.items():
            if node.get("message"):
                message_nodes.append(node)
        
        # Sort by create_time if available
        message_nodes.sort(key=lambda n: n["message"].get("create_time") or 0)
        
        for node in message_nodes:
            msg_data = node.get("message", {})
            if not msg_data:
                continue
            
            # Get author role
            author = msg_data.get("author", {})
            if isinstance(author, str):
                role = author
            else:
                role = author.get("role", "unknown")
            
            # Skip system/tool messages if they're empty or metadata
            if role in ("system", "tool"):
                content_check = msg_data.get("content", {})
                if isinstance(content_check, dict) and not content_check.get("parts"):
                    continue
                elif isinstance(content_check, str) and not content_check.strip():
                    continue
            
            # Get content - handle multiple formats
            content_data = msg_data.get("content", {})
            content = ""
            
            # Handle string content directly
            if isinstance(content_data, str):
                content = content_data
            # Handle dict with parts
            elif isinstance(content_data, dict):
                content_parts = content_data.get("parts", [])
                if content_parts:
                    # Join all text parts
                    text_parts = []
                    for part in content_parts:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            # Handle different content types
                            if "text" in part:
                                text_parts.append(part["text"])
                            elif "content" in part:
                                text_parts.append(str(part["content"]))
                    content = "\n".join(text_parts)
                # Try direct text field
                elif "text" in content_data:
                    content = str(content_data["text"])
            
            # Skip empty messages
            if not content or not content.strip():
                continue
            
            # Parse timestamp
            timestamp = None
            if msg_data.get("create_time"):
                try:
                    timestamp = datetime.fromtimestamp(msg_data["create_time"])
                except (ValueError, TypeError, OSError):
                    pass
            
            # Get model info
            model = msg_data.get("metadata", {}).get("model_slug")
            
            messages.append(Message(
                id=msg_data.get("id", "unknown"),
                role=role,
                content=content,
                timestamp=timestamp,
                model=model
            ))
        
        return messages
    
    def search(self, query: str, case_sensitive: bool = False) -> List[Conversation]:
        """Search conversations by content or title"""
        results = []
        search_query = query if case_sensitive else query.lower()
        
        for conv in self.conversations:
            searchable = conv.title if case_sensitive else conv.title.lower()
            if search_query in searchable:
                results.append(conv)
                continue
            
            for msg in conv.messages:
                msg_content = msg.content if case_sensitive else msg.content.lower()
                if search_query in msg_content:
                    results.append(conv)
                    break
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the parsed data"""
        total_messages = sum(len(c.messages) for c in self.conversations)
        total_words = sum(c.word_count() for c in self.conversations)
        
        models_used = {}
        for conv in self.conversations:
            if conv.model:
                models_used[conv.model] = models_used.get(conv.model, 0) + 1
        
        return {
            "total_conversations": len(self.conversations),
            "total_projects": len(self.projects),
            "unassigned_conversations": len(self.unassigned_conversations),
            "total_messages": total_messages,
            "total_words": total_words,
            "models_used": models_used
        }
    
    def export_to_markdown(self, output_dir: str) -> None:
        """Export all conversations to markdown files"""
        os.makedirs(output_dir, exist_ok=True)
        
        # Export by project
        for project_id, project in self.projects.items():
            project_dir = os.path.join(output_dir, self._sanitize_filename(project.name))
            os.makedirs(project_dir, exist_ok=True)
            
            for conv in project.conversations:
                filename = self._sanitize_filename(conv.title) + ".md"
                filepath = os.path.join(project_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(conv.to_markdown())
        
        # Export unassigned conversations
        if self.unassigned_conversations:
            unassigned_dir = os.path.join(output_dir, "_Unassigned")
            os.makedirs(unassigned_dir, exist_ok=True)
            
            for conv in self.unassigned_conversations:
                filename = self._sanitize_filename(conv.title) + ".md"
                filepath = os.path.join(unassigned_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(conv.to_markdown())
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename"""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        # Limit length
        if len(name) > 100:
            name = name[:100]
        return name.strip() or "untitled"


def main():
    """CLI entry point"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python parser.py <path_to_chatgpt_export>")
        print("       python parser.py <path_to_chatgpt_export> --export <output_dir>")
        sys.exit(1)
    
    export_path = sys.argv[1]
    
    print(f"📂 Parsing ChatGPT export from: {export_path}")
    parser = ChatGPTParser(export_path)
    parser.parse()
    
    stats = parser.get_stats()
    print("\n📊 Statistics:")
    print(f"   Total Conversations: {stats['total_conversations']}")
    print(f"   Total Projects: {stats['total_projects']}")
    print(f"   Unassigned Conversations: {stats['unassigned_conversations']}")
    print(f"   Total Messages: {stats['total_messages']}")
    print(f"   Total Words: {stats['total_words']:,}")
    
    if stats['models_used']:
        print("\n🤖 Models Used:")
        for model, count in sorted(stats['models_used'].items(), key=lambda x: -x[1]):
            print(f"   {model}: {count}")
    
    # Export if requested
    if "--export" in sys.argv:
        export_idx = sys.argv.index("--export")
        if export_idx + 1 < len(sys.argv):
            output_dir = sys.argv[export_idx + 1]
        else:
            output_dir = os.path.join(export_path, "markdown_export")
        
        print(f"\n📝 Exporting to markdown: {output_dir}")
        parser.export_to_markdown(output_dir)
        print("✅ Export complete!")


if __name__ == "__main__":
    main()
