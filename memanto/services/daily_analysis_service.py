import logging
from typing import List, Optional

from memanto.models import Session
from memanto.services import EmbeddingService

logger = logging.getLogger(__name__)

class DailyAnalysisService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    async def generate_summary(
        self,
        sessions: List[Session],
        header_prompt: str,
        footer_prompt: str,
        max_chunk_size: int = 6000,
    ) -> str:
        """
        Generate a summary for a day's sessions, handling large content by splitting into chunks.

        Args:
            sessions: List of sessions for the day
            header_prompt: Instructions for the summarization
            footer_prompt: Markdown output contract
            max_chunk_size: Maximum size for embedding chunks (default: 6000 chars)

        Returns:
            The generated summary
        """
        # Combine all session summaries into a single text
        session_text = "\n\n".join([session.summary for session in sessions])

        # Split the session text into chunks that fit within the embedding context window
        chunks = self._split_text(session_text, max_chunk_size)

        # Process each chunk and combine the results
        summaries = []
        for chunk in chunks:
            try:
                # Create the query for this chunk
                query = f"{header_prompt}\n\n{chunk}\n\n{footer_prompt}"

                # Generate the summary for this chunk
                summary = await self.embedding_service.generate(query=query)
                summaries.append(summary)
            except Exception as e:
                logger.error(f"Failed to generate summary for chunk: {e}")
                raise

        # Combine all chunk summaries into a final summary
        final_summary = "\n\n".join(summaries)
        return final_summary

    def _split_text(self, text: str, max_chunk_size: int) -> List[str]:
        """
        Split text into chunks of approximately max_chunk_size characters.

        Args:
            text: The text to split
            max_chunk_size: Maximum size for each chunk

        Returns:
            List of text chunks
        """
        chunks = []
        current_chunk = ""

        for sentence in text.split("\n"):
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += sentence + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks