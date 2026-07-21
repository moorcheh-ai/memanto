import re
from typing import Optional, Union, List, Dict, Any
from .types import InputLimits, RecallResult, AnswerResult

class DirectClient:
    # ... existing code ...

    def _validate_query(self, query: str, limit: Optional[int] = None) -> None:
        """Validate the query and limit parameters."""
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or blank.")

        if len(query) > InputLimits.MAX_QUERY_LENGTH:
            raise ValueError(f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters.")

        if limit is not None:
            if not isinstance(limit, int) or limit < 1 or limit > InputLimits.MAX_RECALL_LIMIT:
                raise ValueError(f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}.")

    def recall(self, query: str, limit: int = 10) -> RecallResult:
        """Recall relevant information from memory."""
        self._validate_query(query, limit)
        # ... existing recall implementation ...

    def answer(self, question: str, limit: int = 10) -> AnswerResult:
        """Answer a question using information from memory."""
        self._validate_query(question, limit)
        # ... existing answer implementation ...

class SdkClient:
    # ... existing code ...

    def _validate_query(self, query: str, limit: Optional[int] = None) -> None:
        """Validate the query and limit parameters."""
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or blank.")

        if len(query) > InputLimits.MAX_QUERY_LENGTH:
            raise ValueError(f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters.")

        if limit is not None:
            if not isinstance(limit, int) or limit < 1 or limit > InputLimits.MAX_RECALL_LIMIT:
                raise ValueError(f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}.")

    def recall(self, query: str, limit: int = 10) -> RecallResult:
        """Recall relevant information from memory."""
        self._validate_query(query, limit)
        # ... existing recall implementation ...

    def answer(self, question: str, limit: int = 10) -> AnswerResult:
        """Answer a question using information from memory."""
        self._validate_query(question, limit)
        # ... existing answer implementation ...