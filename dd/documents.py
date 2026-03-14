# drift-detector/dd/documents.py

"""
Document and testrun CRUD routes.

All external references use UUIDv7 extids. Integer primary keys
and foreign keys are stripped from API responses.
"""

from fastapi import APIRouter, HTTPException, Request

import dd.store as store
from dd.auth import get_session_hash
from dd.extid import externalize

router = APIRouter()


def _ext_doc(doc):
    """Externalize a document row for API response."""
    return externalize(doc, exclude=("id", "session_hash"))


def _ext_testrun(tr):
    """Externalize a testrun row for API response."""
    return externalize(tr, exclude=("id", "document_id"))


def _ext_doc_list(doc):
    """Externalize a document row from the list query (includes aggregates)."""
    return externalize(doc, exclude=("id", "session_hash"))


@router.post("/api/save")
async def save_testrun(payload: dict, request: Request):
    """Save current state as a new testrun within a document.

    Payload: {state: {...}, documentExtid: str|null, testrunType: "save"|"autosave",
              testrunExtid: str|null,
              blobHash: str|null, encryptedBlob: str|null, blobIv: str|null,
              endpointCount: int|null, driftCount: int|null, okCount: int|null}
    - If documentExtid is null: creates a new document + first testrun.
    - If documentExtid is set: appends a new testrun to that document.

    Returns: {ok, document: {...}, testrun: {...}}
    """
    session_hash = get_session_hash(request)
    state = payload.get("state", payload)
    document_extid = payload.get("documentExtid")
    testrun_type = payload.get("testrunType", "save")
    testrun_extid = payload.get("testrunExtid")
    blob_hash = payload.get("blobHash")
    encrypted_blob = payload.get("encryptedBlob")
    blob_iv = payload.get("blobIv")
    endpoint_count = payload.get("endpointCount")
    drift_count = payload.get("driftCount")
    ok_count = payload.get("okCount")
    result = store.save(
        state,
        document_extid=document_extid,
        testrun_type=testrun_type,
        testrun_extid=testrun_extid,
        session_hash=session_hash,
        blob_hash=blob_hash,
        encrypted_blob=encrypted_blob,
        blob_iv=blob_iv,
        endpoint_count=endpoint_count,
        drift_count=drift_count,
        ok_count=ok_count,
    )
    skipped = result.get("testrun", {}).get("skipped", False)
    if skipped:
        return {"ok": True, "skipped": True}
    return {
        "ok": True,
        "document": _ext_doc(result["document"]),
        "testrun": _ext_testrun(result["testrun"]),
    }


@router.get("/api/documents")
async def list_documents(request: Request):
    """List all documents with testrun counts, filtered by session token."""
    session_hash = get_session_hash(request)
    docs = store.list_documents(session_hash=session_hash)
    return {"documents": [_ext_doc_list(d) for d in docs]}


@router.get("/api/documents/{doc_extid}")
async def get_document(doc_extid: str, request: Request):
    session_hash = get_session_hash(request)
    doc = store.get_document_by_extid(doc_extid)
    if not doc or doc.get("session_hash") != session_hash:
        raise HTTPException(status_code=404, detail="Document not found")
    testruns = store.list_testruns(doc["id"])
    return {
        "document": _ext_doc(doc),
        "testruns": [_ext_testrun(t) for t in testruns],
    }


@router.patch("/api/documents/{doc_extid}")
async def update_document(doc_extid: str, payload: dict, request: Request):
    """Update a document's title."""
    session_hash = get_session_hash(request)
    doc = store.get_document_by_extid(doc_extid)
    if not doc or doc.get("session_hash") != session_hash:
        raise HTTPException(status_code=404, detail="Document not found")
    title = payload.get("title")
    if title is not None:
        store.update_document_title(doc["id"], title)
    doc = store.get_document_by_extid(doc_extid)
    return {"ok": True, "document": _ext_doc(doc)}


@router.get("/api/documents/{doc_extid}/testruns")
async def list_testruns(doc_extid: str, request: Request):
    session_hash = get_session_hash(request)
    doc = store.get_document_by_extid(doc_extid)
    if not doc or doc.get("session_hash") != session_hash:
        raise HTTPException(status_code=404, detail="Document not found")
    testruns = store.list_testruns(doc["id"])
    return {"testruns": [_ext_testrun(t) for t in testruns]}


@router.get("/api/documents/{doc_extid}/testruns/{testrun_extid}")
async def get_testrun(doc_extid: str, testrun_extid: str, request: Request):
    """Get a specific testrun by extid."""
    session_hash = get_session_hash(request)
    doc = store.get_document_by_extid(doc_extid)
    if not doc or doc.get("session_hash") != session_hash:
        raise HTTPException(status_code=404, detail="Document not found")
    testrun = store.get_testrun_by_extid(testrun_extid)
    if not testrun:
        raise HTTPException(status_code=404, detail="Testrun not found")
    return {"testrun": _ext_testrun(testrun)}


@router.delete("/api/documents/{doc_extid}/testruns/{testrun_extid}")
async def delete_testrun(doc_extid: str, testrun_extid: str, request: Request):
    """Soft-delete a testrun."""
    session_hash = get_session_hash(request)
    doc = store.get_document_by_extid(doc_extid)
    if not doc or doc.get("session_hash") != session_hash:
        raise HTTPException(status_code=404, detail="Document not found")
    ok = store.soft_delete_testrun_by_extid(testrun_extid)
    if not ok:
        raise HTTPException(status_code=404, detail="Testrun not found or already deleted")
    return {"ok": True}
