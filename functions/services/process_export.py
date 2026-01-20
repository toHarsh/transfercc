"""
Service module for processing ChatGPT export files.

This module contains the core business logic for parsing and processing
ChatGPT export files (ZIP or JSON). It can be used by both direct upload
endpoints and background workers (e.g., GCS-triggered functions).
"""
import os
import json
import zipfile
import logging
import tempfile
from typing import Union, Dict, Any, BinaryIO
from io import BytesIO

logger = logging.getLogger(__name__)

# Import parser - will be available in the functions environment
try:
    from parser import ChatGPTParser
except ImportError:
    logger.error("Failed to import ChatGPTParser")
    raise


def process_export(
    job_id: str,
    file_handle_or_bytes: Union[str, BinaryIO, bytes],
    *,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Process a ChatGPT export file and return summary statistics.
    
    This is the core processing function that:
    1. Extracts data from ZIP or JSON files
    2. Normalizes the data structure
    3. Parses conversations using ChatGPTParser
    4. Returns summary statistics
    
    Args:
        job_id: Unique identifier for this processing job
        file_handle_or_bytes: Can be:
            - File path (str) to a local file
            - File-like object (BinaryIO) with read() method
            - bytes object containing file data
        metadata: Optional dict with additional info like:
            - filename: Original filename
            - content_type: MIME type
            - file_size: Size in bytes
    
    Returns:
        Dict with:
            - success: bool
            - stats: Dict with conversation/message counts
            - error: str (if processing failed)
            - conversations_data: List of parsed conversations (for storage)
    
    Raises:
        ValueError: If file format is invalid or no conversations found
        Exception: For other processing errors
    """
    metadata = metadata or {}
    filename = metadata.get('filename', 'unknown')
    filename_lower = filename.lower()
    
    logger.info(f"[Job {job_id}] Starting export processing for {filename}")
    
    try:
        # Extract data from file based on type
        if isinstance(file_handle_or_bytes, str):
            # File path - read from filesystem
            data = _extract_from_file_path(file_handle_or_bytes, filename_lower)
        elif isinstance(file_handle_or_bytes, bytes):
            # Bytes - create BytesIO wrapper
            data = _extract_from_bytes(file_handle_or_bytes, filename_lower)
        elif hasattr(file_handle_or_bytes, 'read'):
            # File-like object (e.g., GCS blob)
            data = _extract_from_file_like(file_handle_or_bytes, filename_lower)
        else:
            raise ValueError(f"Unsupported file input type: {type(file_handle_or_bytes)}")
        
        logger.info(f"[Job {job_id}] Extracted data, type: {type(data)}, length: {len(data) if isinstance(data, list) else 'N/A'}")
        
        # Normalize data structure
        normalized_data = _normalize_data_structure(data)
        logger.info(f"[Job {job_id}] Normalized to {len(normalized_data)} conversations")
        
        if len(normalized_data) == 0:
            raise ValueError("No conversations found in the file")
        
        # Parse conversations
        logger.info(f"[Job {job_id}] Parsing {len(normalized_data)} conversations...")
        parser = ChatGPTParser()
        parser.parse_from_json(normalized_data)
        
        if len(parser.conversations) == 0:
            raise ValueError("No conversations with messages found after parsing")
        
        # Get statistics
        stats = parser.get_stats()
        logger.info(f"[Job {job_id}] Processing complete: {stats['total_conversations']} conversations, {stats['total_messages']} messages")
        
        return {
            "success": True,
            "stats": stats,
            "conversations_data": normalized_data,  # Store the raw data for later use
            "parser": parser  # Return parser instance if needed
        }
        
    except Exception as e:
        logger.exception(f"[Job {job_id}] Error processing export: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


def _extract_from_file_path(file_path: str, filename_lower: str) -> list:
    """Extract conversation data from a file path."""
    if filename_lower.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            conversations_json = None
            for name in zip_ref.namelist():
                if name.endswith('conversations.json'):
                    conversations_json = name
                    break
            
            if not conversations_json:
                raise ValueError("No conversations.json found in ZIP file")
            
            with zip_ref.open(conversations_json) as f:
                return json.load(f)
    elif filename_lower.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        raise ValueError(f"Unsupported file type: {filename_lower}")


def _extract_from_bytes(file_bytes: bytes, filename_lower: str) -> list:
    """Extract conversation data from bytes."""
    if filename_lower.endswith('.zip'):
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zip_ref:
            conversations_json = None
            for name in zip_ref.namelist():
                if name.endswith('conversations.json'):
                    conversations_json = name
                    break
            
            if not conversations_json:
                raise ValueError("No conversations.json found in ZIP file")
            
            with zip_ref.open(conversations_json) as f:
                return json.load(f)
    elif filename_lower.endswith('.json'):
        return json.loads(file_bytes.decode('utf-8'))
    else:
        raise ValueError(f"Unsupported file type: {filename_lower}")


def _extract_from_file_like(file_obj: BinaryIO, filename_lower: str) -> list:
    """Extract conversation data from a file-like object."""
    if filename_lower.endswith('.zip'):
        # Read all data into memory for ZIP processing
        file_data = file_obj.read()
        with zipfile.ZipFile(BytesIO(file_data), 'r') as zip_ref:
            conversations_json = None
            for name in zip_ref.namelist():
                if name.endswith('conversations.json'):
                    conversations_json = name
                    break
            
            if not conversations_json:
                raise ValueError("No conversations.json found in ZIP file")
            
            with zip_ref.open(conversations_json) as f:
                return json.load(f)
    elif filename_lower.endswith('.json'):
        return json.load(file_obj)
    else:
        raise ValueError(f"Unsupported file type: {filename_lower}")


def _normalize_data_structure(data: Any) -> list:
    """
    Normalize ChatGPT export data structure to a list of conversations.
    
    Handles various formats:
    - Direct list of conversations
    - Dict with 'conversations' key
    - Dict with 'data' key
    - Dict with nested conversation lists
    """
    if isinstance(data, list):
        return data
    
    if isinstance(data, dict):
        # Try common keys
        if "conversations" in data:
            return data["conversations"]
        elif "data" in data:
            return data["data"]
        else:
            # Look for nested lists that look like conversations
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0:
                    # Check if first item looks like a conversation
                    first_item = value[0]
                    if isinstance(first_item, dict) and (
                        "id" in first_item or 
                        "conversation_id" in first_item or 
                        "mapping" in first_item
                    ):
                        return value
    
    raise ValueError("Invalid data format. Expected a list of conversations or a dict containing conversations.")
