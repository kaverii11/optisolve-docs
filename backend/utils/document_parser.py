"""
Local, deterministic document parsing and chunking for the knowledge base.

No LLM calls here: parsing runs on every upload and the Groq free tier
(1,000 req/day, 8,000 TPM) is reserved for ticket replies.
"""
import io
import os
import re
from dataclasses import dataclass

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# all-MiniLM-L6-v2 truncates input at 256 word pieces (~1,000-1,200 characters of
# English), so anything past that in a chunk would never reach the embedding.
DEFAULT_MAX_CHUNK_CHARS = 1000


class UnsupportedDocumentError(ValueError):
    pass


@dataclass
class Block:
    text: str
    is_heading: bool = False


def parse_document(filename: str, data: bytes) -> list[Block]:
    extension = os.path.splitext(filename or "")[1].lower()
    if extension == ".pdf":
        return _parse_pdf(data)
    if extension == ".docx":
        return _parse_docx(data)
    if extension == ".txt":
        return _parse_txt(data)
    raise UnsupportedDocumentError(
        f"Unsupported file type '{extension or filename}'. Use PDF, DOCX or TXT."
    )


def _raw_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.split(r"\n\s*\n", text)


_MARKDOWN_HEADING = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")


def _plain_heading(line: str) -> str | None:
    """
    A short title-like line with no closing punctuation, e.g. "Guest Wi-Fi for
    visitors". Wrapped body lines are long or end a sentence, so they don't match.
    """
    line = line.strip()
    if not line or len(line) > 80 or len(line.split()) > 10:
        return None
    if not (line[0].isupper() or line[0].isdigit()):
        return None
    if line[-1] in ".,;:!?)\"'" or line[0] in "-*•":
        return None
    return line


def _text_to_blocks(text: str) -> list[Block]:
    # Headings are found per line, not per paragraph, because the body usually
    # follows a heading on the very next line (and PDFs rarely have blank lines).
    blocks = []
    raw_blocks = [raw for raw in _raw_paragraphs(text) if raw.strip()]
    for block_index, raw in enumerate(raw_blocks):
        lines = [line for line in raw.split("\n") if line.strip()]
        body: list[str] = []
        for i, line in enumerate(lines):
            match = _MARKDOWN_HEADING.match(line)
            heading = match.group(1) if match else None
            if heading is None and (i + 1 < len(lines) or block_index + 1 < len(raw_blocks)):
                # A plain heading needs body text after it, in this block or the next.
                heading = _plain_heading(line)
            if heading is None:
                body.append(line)
                continue
            if body:
                blocks.append(Block(" ".join(" ".join(body).split())))
                body = []
            blocks.append(Block(heading, is_heading=True))
        if body:
            blocks.append(Block(" ".join(" ".join(body).split())))
    return blocks


def _parse_txt(data: bytes) -> list[Block]:
    return _text_to_blocks(data.decode("utf-8-sig", errors="replace"))


def _parse_pdf(data: bytes) -> list[Block]:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return _text_to_blocks("\n\n".join(pages))


def _parse_docx(data: bytes) -> list[Block]:
    document = DocxDocument(io.BytesIO(data))
    blocks = []
    for paragraph in document.paragraphs:
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        style_name = (paragraph.style.name or "") if paragraph.style is not None else ""
        is_heading = style_name.startswith("Heading") or style_name == "Title"
        blocks.append(Block(text, is_heading=is_heading))
    return blocks


def _split_oversized(text: str, max_chars: int) -> list[str]:
    """Split one paragraph that is too long: at sentence ends, then at words."""
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            words = sentence.split()
            line = ""
            for word in words:
                if line and len(line) + 1 + len(word) > max_chars:
                    pieces.append(line)
                    line = word
                else:
                    line = f"{line} {word}" if line else word
            if line:
                pieces.append(line)
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_blocks(blocks: list[Block], max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[str]:
    """
    Pack whole paragraphs into chunks of at most max_chars, never across a
    section heading. Each chunk is prefixed with its section heading so the
    embedding keeps the topic even when the paragraph text doesn't repeat it.
    """
    chunks: list[str] = []
    heading = ""
    body: list[str] = []

    def prefix() -> str:
        return f"{heading}\n" if heading else ""

    def flush():
        if body:
            chunks.append(prefix() + "\n".join(body))
            body.clear()

    for block in blocks:
        if block.is_heading:
            flush()
            heading = block.text[: max_chars // 4]
            continue

        budget = max_chars - len(prefix())
        for piece in _split_oversized(block.text, budget) if len(block.text) > budget else [block.text]:
            used = sum(len(p) for p in body) + max(len(body) - 1, 0)
            if body and used + 1 + len(piece) > budget:
                flush()
            body.append(piece)

    flush()
    return chunks
