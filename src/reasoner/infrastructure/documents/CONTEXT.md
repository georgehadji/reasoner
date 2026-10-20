# Context: Documents

## Directory: `src/reasoner/infrastructure/documents`

## Description
Implementations for reading and extracting contents from specialized document types (PDFs, Docx, HTML).

## Files
- **`__init__.py`**: Python package initialization module.
- **`index_queue.py`**: Bounded background queue for document semantic-search indexing.
- **`parse_worker.py`**: PDF/DOCX text extraction run as a child process the uploader can kill on timeout; memory-capped on Linux; refuses zip bombs.

## Subfolders
*No subfolders in this directory.*
