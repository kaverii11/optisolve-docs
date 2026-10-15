import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.utils.document_parser import (
    SUPPORTED_EXTENSIONS,
    UnsupportedDocumentError,
    chunk_blocks,
    parse_document,
)
from backend.utils.knowledge_base import add_document_chunks

router = APIRouter(tags=["knowledge-base"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadDocumentResponse(BaseModel):
    filename: str
    chunks_added: int
    characters_parsed: int


@router.post("/knowledge-base/upload", response_model=UploadDocumentResponse)
def upload_document(file: UploadFile = File(...)):
    filename = os.path.basename(file.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported file type. Use PDF, DOCX or TXT.")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB.")

    try:
        blocks = parse_document(filename, data)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=422, detail=f"Could not read {filename}; the file may be corrupt.")

    chunks = chunk_blocks(blocks)
    if not chunks:
        # Typical for scanned PDFs: images only, no text layer to extract.
        raise HTTPException(status_code=422, detail=f"No extractable text found in {filename}.")

    add_document_chunks(filename, chunks)
    return UploadDocumentResponse(
        filename=filename,
        chunks_added=len(chunks),
        characters_parsed=sum(len(block.text) for block in blocks),
    )
