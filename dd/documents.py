# drift-detector/dd/documents.py

"""
Document and testrun CRUD routes.
"""

from fastapi import APIRouter, Request

import dd.store as store
from dd.auth import get_session_hash

router = APIRouter()


@router.post("/api/save")
async def save_testrun(payload: dict, request: Request):
    """Save current state as a new testrun within a document.

    Payload: {state: {...}, documentId: int|null, testrunType: "save"|"autosave"}
    - If documentId is null: creates a new document + first testrun.
    - If documentId is set: appends a new testrun to that document.

    Returns: {ok, document: {...}, testrun: {...}}
    """
    session_hash = get_session_hash(request)
    state = payload.get("state", payload)  # accept both wrapped and bare state
    document_id = payload.get("documentId")
    testrun_type = payload.get("testrunType", "save")
    testrun_number = payload.get("testrunNumber")
    result = store.save(state, document_id, testrun_type=testrun_type, testrun_number=testrun_number, session_hash=session_hash)
    skipped = result.get("testrun", {}).get("skipped", False)
    if skipped:
        return {"ok": True, "skipped": True}
    return {"ok": True, **result}


@router.get("/api/documents")
async def list_documents(request: Request):
    """List all documents with testrun counts, filtered by session token."""
    session_hash = get_session_hash(request)
    return {"documents": store.list_documents(session_hash=session_hash)}


@router.get("/api/documents/{doc_id}")
async def get_document(doc_id: int):
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": "Document not found"}
    testruns = store.list_testruns(doc_id)
    return {"document": doc, "testruns": testruns}


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


@router.get("/api/documents/{doc_id}/testruns")
async def list_testruns(doc_id: int):
    return {"testruns": store.list_testruns(doc_id)}


@router.get("/api/documents/{doc_id}/testruns/{testrun_number}")
async def get_testrun(doc_id: int, testrun_number: int):
    """Get a specific testrun by document ID and testrun number.
    Returns the full state for that testrun."""
    testrun = store.get_testrun_by_number(doc_id, testrun_number)
    if not testrun:
        return {"error": "Testrun not found"}
    return {"testrun": testrun}


@router.delete("/api/documents/{doc_id}/testruns/{testrun_number}")
async def delete_testrun(doc_id: int, testrun_number: int):
    """Soft-delete a testrun."""
    ok = store.soft_delete_testrun(doc_id, testrun_number)
    if not ok:
        return {"ok": False, "error": "Testrun not found or already deleted"}
    return {"ok": True}
