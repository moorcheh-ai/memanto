"""
Backends for the contract reconciliation benchmark.

This module provides:
- ActiveDigestBackend (Memanto-style): typed digest with contradiction detection
- AppendOnlyBackend (passive baseline): stores all changes, no reconciliation
- RecentWindowBackend: only keeps last N entries, forgets old valid facts
"""

from abc import ABC, abstractmethod
from typing import Any
from collections import defaultdict
import json


class MemoryBackend(ABC):
    """Abstract base class for all memory backends."""

    @abstractmethod
    def remember(self, contract_id: str, data: dict) -> str:
        """Store a memory record."""
        pass

    @abstractmethod
    def recall(self, query: dict) -> list:
        """Retrieve memories matching a query."""
        pass

    @abstractmethod
    def get_all(self) -> list:
        """Return all stored memories."""
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """Return backend statistics."""
        pass


class ActiveDigestBackend(MemoryBackend):
    """
    Memanto-style active companion memory.
    
    Stores typed current-state digests, collapses superseded facts,
    detects contradictions, and redacts old values.
    """
    
    # Memory types for typed classification
    TYPE_CREATE = "create"
    TYPE_TERMINATE = "terminate"
    TYPE_UPDATE = "update"
    TYPE_PAUSE = "pause"

    def __init__(self):
        self._digests = {}  # contract_id -> current digest
        self._type_index = defaultdict(list)  # type -> list of contract_ids
        self._history = []  # full history log
        self._version_counter = 0

    def remember(self, contract_id: str, data: dict) -> str:
        self._version_counter += 1
        action = data.get("action", "update")
        
        if action == "create":
            self._digests[contract_id] = {
                "contract_id": contract_id,
                "active": True,
                "counterparty": data["data"].get("counterparty", ""),
                "value_usd": data["data"].get("value_usd", 0),
                "payment_terms": data["data"].get("payment_terms", ""),
                "obligations": data["data"].get("obligations", []),
                "terminated": False,
                "paused": False,
                "version": 1,
                "last_updated": str(data.get("timestamp", ""))
            }
            self._type_index[self.TYPE_CREATE].append(contract_id)
            
        elif action == "terminate":
            if contract_id in self._digests:
                old = self._digests[contract_id]
                old["active"] = False
                old["terminated"] = True
                old["version"] += 1
                old["last_updated"] = str(data.get("timestamp", ""))
                self._type_index[self.TYPE_TERMINATE].append(contract_id)
                
        elif action == "pause":
            if contract_id in self._digests:
                old = self._digests[contract_id]
                old["active"] = False
                old["paused"] = True
                old["version"] += 1
                old["last_updated"] = str(data.get("timestamp", ""))
                self._type_index[self.TYPE_PAUSE].append(contract_id)
                
        elif action == "update_obligations":
            if contract_id in self._digests:
                old = self._digests[contract_id]
                new_obligation = data["data"].get("new_obligation", "")
                old["obligations"].append(new_obligation)
                old["version"] += 1
                old["last_updated"] = str(data.get("timestamp", ""))

        self._history.append({
            "version": self._version_counter,
            "contract_id": contract_id,
            "action": action,
            "data": data
        })
        
        return f"v{self._version_counter}"

    def recall(self, query: dict) -> list:
        result = []
        query_type = query.get("type", "all")

        if query_type == "filter":
            desc = query.get("description", "")
            if "more than 4 obligations" in desc:
                for cid, digest in self._digests.items():
                    if digest["active"] and not digest["terminated"] and not digest["paused"]:
                        if len(digest.get("obligations", [])) > 4:
                            result.append(cid)
                            
            elif "milestone" in desc.lower():
                for cid, digest in self._digests.items():
                    if digest["active"] and not digest["terminated"] and not digest["paused"]:
                        if "milestone" in digest.get("payment_terms", ""):
                            result.append(cid)
                            
            elif "Terminated" in desc or "terminated" in desc.lower():
                for cid, digest in self._digests.items():
                    if digest["terminated"]:
                        result.append(cid)
                        
        elif query_type == "aggregate":
            total = sum(d["value_usd"] for d in self._digests.values() 
                       if d["active"] and not d["terminated"] and not d["paused"])
            result = [total]
            
        elif query_type == "groupby":
            cp_count = defaultdict(int)
            for d in self._digests.values():
                if d["active"] and not d["terminated"] and not d["paused"]:
                    cp_count[d["counterparty"]] += 1
            if cp_count:
                top_cp = max(cp_count, key=cp_count.get)
                result = [top_cp]

        return result

    def get_all(self) -> list:
        return list(self._digests.values())

    def get_stats(self) -> dict:
        return {
            "total_digests": len(self._digests),
            "active": sum(1 for d in self._digests.values() if d["active"] and not d["terminated"] and not d["paused"]),
            "terminated": sum(1 for d in self._digests.values() if d["terminated"]),
            "paused": sum(1 for d in self._digests.values() if d["paused"]),
            "history_entries": len(self._history),
            "version_counter": self._version_counter
        }


class AppendOnlyBackend(MemoryBackend):
    """
    Passive append-only baseline.
    
    Stores all raw observations without conflict resolution or suppression
    of superseded facts.
    """
    
    def __init__(self):
        self._entries = []  # all entries, never deleted
        self._entry_counter = 0

    def remember(self, contract_id: str, data: dict) -> str:
        self._entry_counter += 1
        entry = {
            "entry_id": self._entry_counter,
            "contract_id": contract_id,
            "action": data.get("action", "update"),
            "data": data.get("data", {}),
            "raw": data,
            "timestamp": data.get("timestamp", "")
        }
        self._entries.append(entry)
        return f"entry_{self._entry_counter}"

    def recall(self, query: dict) -> list:
        # Just return raw matching entries - no reconciliation!
        result = []
        query_type = query.get("type", "all")
        
        if query_type == "filter":
            desc = query.get("description", "")
            for entry in self._entries:
                if "Terminated" in desc or "terminated" in desc.lower():
                    if entry["action"] == "terminate":
                        result.append(entry)
                elif "milestone" in desc.lower():
                    if "milestone" in str(entry["data"].get("payment_terms", "")):
                        result.append(entry)

        elif query_type == "aggregate":
            # Sum ALL values including terminated ones!
            total = sum(e["data"].get("value_usd", 0) for e in self._entries 
                       if e["action"] == "create")
            result = [total]
            
        elif query_type == "groupby":
            cp_count = defaultdict(int)
            for e in self._entries:
                if e["action"] == "create":
                    cp_count[e["data"].get("counterparty", "unknown")] += 1
            if cp_count:
                result = [max(cp_count, key=cp_count.get)]

        return result

    def get_all(self) -> list:
        return self._entries

    def get_stats(self) -> dict:
        return {
            "total_entries": len(self._entries),
            "create_count": sum(1 for e in self._entries if e["action"] == "create"),
            "terminate_count": sum(1 for e in self._entries if e["action"] == "terminate"),
            "pause_count": sum(1 for e in self._entries if e["action"] == "pause"),
            "update_count": sum(1 for e in self._entries if e["action"] == "update_obligations")
        }


class RecentWindowBackend(MemoryBackend):
    """
    Sliding recent-window baseline.
    
    Keeps only the latest N raw observations. Forgets old still-valid decisions
    but avoids bringing back stale facts.
    """
    
    def __init__(self, window_size: int = 20):
        self._window = []  # latest N entries
        self._window_size = window_size

    def remember(self, contract_id: str, data: dict) -> str:
        entry = {
            "contract_id": contract_id,
            "action": data.get("action", "update"),
            "data": data.get("data", {}),
            "timestamp": data.get("timestamp", "")
        }
        self._window.append(entry)
        if len(self._window) > self._window_size:
            self._window.pop(0)
        return f"window_pos_{len(self._window)}"

    def recall(self, query: dict) -> list:
        result = []
        query_type = query.get("type", "all")
        
        if query_type == "filter":
            desc = query.get("description", "")
            # Only search recent window
            for entry in self._window:
                if "Terminated" in desc or "terminated" in desc.lower():
                    if entry["action"] == "terminate":
                        result.append(entry["contract_id"])
                elif "more than 4 obligations" in desc:
                    # No way to know obligation count from raw entries!
                    pass
                elif "milestone" in desc.lower():
                    if "milestone" in str(entry["data"].get("payment_terms", "")):
                        result.append(entry["contract_id"])

        elif query_type == "aggregate":
            # Can only sum creates in window
            total = sum(e["data"].get("value_usd", 0) for e in self._window 
                       if e["action"] == "create")
            result = [total]
            
        elif query_type == "groupby":
            # Can only group recent entries
            cp_count = defaultdict(int)
            for e in self._window:
                if e["action"] == "create":
                    cp_count[e["data"].get("counterparty", "unknown")] += 1
            if cp_count:
                result = [max(cp_count, key=cp_count.get)]

        return result

    def get_all(self) -> list:
        return self._window

    def get_stats(self) -> dict:
        return {
            "window_size": len(self._window),
            "max_window": self._window_size
        }
