"""Recursive character text splitter for document chunking.

Custom implementation that avoids the langchain-core dependency.
Splits text using a hierarchy of separators (paragraph > line > word > character)
and maintains configurable overlap between consecutive chunks.

Designed for Russian and English text using Python native string length
(Unicode code points, not bytes).
"""


class RecursiveCharacterTextSplitter:
    """Split text into chunks using recursive character-based splitting.

    Tries separators in order: paragraph breaks, line breaks, spaces,
    then character-level. Maintains overlap between chunks for context.
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks.

        Args:
            text: The text to split.

        Returns:
            List of text chunks, each at most chunk_size characters.
            Empty or whitespace-only input returns [].
        """
        if not text or not text.strip():
            return []

        chunks = self._split_recursive(text, self.separators)
        return self._merge_with_overlap(chunks)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using separator hierarchy."""
        if len(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []

        # Try each separator
        for i, sep in enumerate(separators):
            if sep == "":
                # Character-level split as last resort
                return [
                    text[j:j + self.chunk_size]
                    for j in range(0, len(text), self.chunk_size)
                ]

            if sep in text:
                parts = text.split(sep)
                result = []
                current = ""

                for part in parts:
                    candidate = current + sep + part if current else part
                    if len(candidate) <= self.chunk_size:
                        current = candidate
                    else:
                        if current:
                            result.append(current.strip())
                        # If single part exceeds chunk_size, split deeper
                        if len(part) > self.chunk_size:
                            result.extend(
                                self._split_recursive(
                                    part, separators[i + 1:]
                                )
                            )
                            current = ""
                        else:
                            current = part

                if current and current.strip():
                    result.append(current.strip())

                if result:
                    return result

        return [text]

    def _merge_with_overlap(self, chunks: list[str]) -> list[str]:
        """Add overlap between consecutive chunks."""
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            # Take overlap from end of previous chunk
            prev = chunks[i - 1]
            overlap_text = prev[-self.chunk_overlap:] if len(prev) > self.chunk_overlap else prev
            merged = overlap_text + " " + chunks[i]

            # Trim if merged exceeds chunk_size
            if len(merged) > self.chunk_size:
                merged = merged[:self.chunk_size]

            result.append(merged.strip())

        return [c for c in result if c]
