"""Multi-format document parser for knowledge base ingestion.

Extracts plain text from .txt, .md, .pdf, .docx, and .html files.
All methods accept bytes and return str. Synchronous -- caller wraps
in asyncio.to_thread() for async context.
"""

import io
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument
from bs4 import BeautifulSoup


class DocumentParser:
    """Extracts plain text from various document formats.

    Supported: .txt, .md, .pdf, .docx, .html
    All methods accept bytes and return str.
    """

    SUPPORTED_EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.html'}

    @staticmethod
    def parse(filename: str, content: bytes) -> str:
        """Dispatch to format-specific parser based on file extension.

        Args:
            filename: Original filename (used for extension detection).
            content: Raw file bytes.

        Returns:
            Extracted plain text.

        Raises:
            ValueError: If file extension is not supported.
        """
        ext = Path(filename).suffix.lower()

        if ext in ('.txt', '.md'):
            return content.decode('utf-8', errors='replace')
        elif ext == '.pdf':
            return DocumentParser._parse_pdf(content)
        elif ext == '.docx':
            return DocumentParser._parse_docx(content)
        elif ext == '.html':
            return DocumentParser._parse_html(content)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @staticmethod
    def _parse_pdf(content: bytes) -> str:
        """Extract text from PDF using PyMuPDF."""
        doc = pymupdf.open(stream=content, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)

    @staticmethod
    def _parse_docx(content: bytes) -> str:
        """Extract text from DOCX using python-docx."""
        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(
            paragraph.text for paragraph in doc.paragraphs
            if paragraph.text.strip()
        )

    @staticmethod
    def _parse_html(content: bytes) -> str:
        """Extract text from HTML using BeautifulSoup.

        Removes script and style elements before text extraction
        to avoid including JavaScript/CSS content.
        """
        soup = BeautifulSoup(content, 'html.parser')
        # Remove script and style elements before get_text()
        for element in soup(['script', 'style']):
            element.decompose()
        return soup.get_text(separator="\n", strip=True)
