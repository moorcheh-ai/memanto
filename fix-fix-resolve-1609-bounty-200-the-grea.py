#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix-fix-resolve-1609-bounty-200-the-grea.py

Memory Migration Utility for Memanto + OKF
-------------------------------------------
Addresses issue #1609: The Great Memory Migration.
Migrates agentic memory data from various formats (JSON, TXT, MD) into the 
standardized OKF (Open Knowledge Format) document structure.

Features:
- Supports multiple JSON structures (lists, single dicts, nested 'memories' keys)
- Splits text and markdown files into separate entries
- Generates stable entry identifiers, timestamps, and integrity checksums
- Validates inputs and handles errors gracefully

Usage:
    python fix-fix-resolve-1609-bounty-200-the-grea.py <input_path> <output_path>

Example:
    python fix-fix-resolve-1609-bounty-200-the-grea.py ./old_memory.json ./okf_memory.json
"""

import os
import sys
import json
import hashlib
import uuid
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Constants for OKF formatting
OKF_VERSION = "1.0.0"
OKF_SCHEMA = "okf/memanto/memory/v1"


def generate_entry_id(content: str) -> str:
    """
    Generate a stable unique identifier for an entry based on its content.
    
    Args:
        content: The text content of the memory entry.
        
    Returns:
        A stable UUID string based on a SHA256 hash of the content.
    """
    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    # Use the first 16 bytes (32 hex chars) to form a UUID
    return str(uuid.UUID(content_hash[:32]))


def generate_checksum(data: Any) -> str:
    """
    Generate an integrity checksum for the OKF document or entry.
    
    Args:
        data: The data to checksum (will be JSON serialized with sorted keys).
        
    Returns:
        A SHA256 hexdigest string representing the data integrity.
    """
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(serialized).hexdigest()


def get_current_timestamp() -> str:
    """
    Get the current UTC timestamp in ISO 8601 format.
    
    Returns:
        Current timestamp string in ISO 8601 format with timezone info.
    """
    return datetime.now(timezone.utc).isoformat()


def create_okf_entry(content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a single OKF-compliant memory entry.
    
    Args:
        content: The text content of the memory.
        metadata: Optional additional metadata to include.
        
    Returns:
        A dictionary representing an OKF entry with id, content, metadata, and checksum.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Entry content must be a non-empty string.")
    
    timestamp = get_current_timestamp()
    entry_id = generate_entry_id(content)
    
    entry = {
        "id": entry_id,
        "content": content.strip(),
        "created_at": timestamp,
        "updated_at": timestamp,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
    
    # Add checksum for integrity verification
    entry["checksum"] = generate_checksum({
        "id": entry["id"],
        "content": entry["content"],
        "created_at": entry["created_at"],
        "updated_at": entry["updated_at"],
    })
    
    return entry


def parse_json_file(file_path: str) -> List[str]:
    """
    Parse a JSON file and extract memory entries.
    Supports multiple structures:
    - List of strings
    - List of objects with 'content' key
    - Single object with 'memories' key containing a list
    - Single string
    
    Args:
        file_path: Path to the JSON file.
        
    Returns:
        A list of memory content strings.
        
    Raises:
        ValueError: If the JSON structure is unsupported or invalid.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in file {file_path}: {e}")
    except Exception as e:
        raise ValueError(f"Error reading file {file_path}: {e}")
    
    entries = []
    
    if isinstance(data, str):
        # Single string
        entries.append(data)
    elif isinstance(data, list):
        # List of items
        for item in data:
            if isinstance(item, str):
                entries.append(item)
            elif isinstance(item, dict):
                # Extract content from common keys
                content = item.get('content') or item.get('text') or item.get('memory')
                if content and isinstance(content, str):
                    entries.append(content)
                else:
                    raise ValueError(f"Unsupported object structure in list: missing 'content', 'text', or 'memory' key")
            else:
                raise ValueError(f"Unsupported item type in list: {type(item)}")
    elif isinstance(data, dict):
        # Check for 'memories' key
        if 'memories' in data and isinstance(data['memories'], list):
            for item in data['memories']:
                if isinstance(item, str):
                    entries.append(item)
                elif isinstance(item, dict):
                    content = item.get('content') or item.get('text') or item.get('memory')
                    if content and isinstance(content, str):
                        entries.append(content)
                    else:
                        raise ValueError(f"Unsupported object structure in 'memories' list: missing content key")
                else:
                    raise ValueError(f"Unsupported item type in 'memories' list: {type(item)}")
        elif 'content' in data and isinstance(data['content'], str):
            # Single object with content
            entries.append(data['content'])
        elif 'text' in data and isinstance(data['text'], str):
            entries.append(data['text'])
        else:
            raise ValueError("Unsupported JSON object structure. Expected 'memories', 'content', or 'text' key.")
    else:
        raise ValueError(f"Unsupported JSON root type: {type(data)}")
    
    if not entries:
        raise ValueError("No memory entries found in the JSON file.")
    
    return entries


def parse_text_file(file_path: str, delimiter: str = '\n\n') -> List[str]:
    """
    Parse a plain text file and split into memory entries.
    Entries are separated by double newlines by default.
    
    Args:
        file_path: Path to the text file.
        delimiter: String used to separate entries (default: double newline).
        
    Returns:
        A list of memory content strings.
        
    Raises:
        ValueError: If the file is empty or cannot be read.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise ValueError(f"Error reading file {file_path}: {e}")
    
    if not content.strip():
        raise ValueError(f"File {file_path} is empty or contains only whitespace.")
    
    entries = [entry.strip() for entry in content.split(delimiter) if entry.strip()]
    
    if not entries:
        raise ValueError(f"No valid entries found in text file {file_path}.")
    
    return entries


def parse_markdown_file(file_path: str) -> List[str]:
    """
    Parse a Markdown file and split into memory entries.
    Entries are separated by Markdown headers (lines starting with '#').
    
    Args:
        file_path: Path to the Markdown file.
        
    Returns:
        A list of memory content strings (each starting with its header).
        
    Raises:
        ValueError: If the file is empty or cannot be read.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise ValueError(f"Error reading file {file_path}: {e}")
    
    if not content.strip():
        raise ValueError(f"File {file_path} is empty or contains only whitespace.")
    
    lines = content.split('\n')
    entries = []
    current_entry_lines = []
    
    for line in lines:
        # Detect headers (lines starting with #)
        if line.strip().startswith('#') and current_entry_lines:
            # Save the previous entry and start a new one
            entry = '\n'.join(current_entry_lines).strip()
            if entry:
                entries.append(entry)
            current_entry_lines = []
        current_entry_lines.append(line)
    
    # Add the last entry
    if current_entry_lines:
        entry = '\n'.join(current_entry_lines).strip()
        if entry:
            entries.append(entry)
    
    if not entries:
        raise ValueError(f"No valid entries found in Markdown file {file_path}.")
    
    return entries


def create_okf_document(source_file: str, entries: List[str]) -> Dict[str, Any]:
    """
    Create a complete OKF document from memory entries.
    
    Args:
        source_file: Path to the source file (for metadata).
        entries: List of memory content strings.
        
    Returns:
        A dictionary representing the complete OKF document.
    """
    okf_entries = []
    for entry_content in entries:
        metadata = {
            "source_file":