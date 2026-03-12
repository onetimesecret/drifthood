"""
Document and session CRUD routes.
"""

from fastapi import APIRouter
import dd.store as store

router = APIRouter()


@router.post("/api/save")
async def save_session(payload: dict):
    """Save current state as a new session within a document.

    Payload: {state: {...}, documentId: int|null, sessionType: "save"|"autosave"}
    - If documentId is null: creates a new document + first session.
    - If documentId is set: appends a new session to that document.

    Returns: {ok, document: {...}, session: {...}}
    """
    state = payload.get("state", payload)  # accept both wrapped and bare state
    document_id = payload.get("documentId")
    session_type = payload.get("sessionType", "save")
    result = store.save(state, document_id, session_type)
    skipped = result.get("session", {}).get("skipped", False)
    if skipped:
        return {"ok": True, "skipped": True}
    return {"ok": True, **result}


@router.get("/api/documents")
async def list_documents():
    """List all documents with session counts."""
    return {"documents": store.list_documents()}


@router.get("/api/documents/{doc_id}")
async def get_document(doc_id: int):
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": "Document not found"}
    sessions = store.list_sessions(doc_id)
    return {"document": doc, "sessions": sessions}


@router.patch("/api/documents/{doc_id}")
async def update_document(doc_id: int, payload: dict):
    """Update a document's title."""
    title = payload.get("title")
    if title is not None:
        store.update_document_title(doc_id, title)
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": "Document not found"}
    return {"ok": True, "document": doc}


@router.get("/api/documents/{doc_id}/sessions")
async def list_sessions(doc_id: int):
    return {"sessions": store.list_sessions(doc_id)}


@router.get("/api/documents/{doc_id}/sessions/{session_number}")
async def get_session(doc_id: int, session_number: int):
    """Get a specific session by document ID and session number.
    Returns the full state for that session."""
    session = store.get_session_by_number(doc_id, session_number)
    if not session:
        return {"error": "Session not found"}
    return {"session": session}


@router.delete("/api/documents/{doc_id}/sessions/{session_number}")
async def delete_session(doc_id: int, session_number: int):
    """Soft-delete a session."""
    ok = store.soft_delete_session(doc_id, session_number)
    if not ok:
        return {"ok": False, "error": "Session not found or already deleted"}
    return {"ok": True}
