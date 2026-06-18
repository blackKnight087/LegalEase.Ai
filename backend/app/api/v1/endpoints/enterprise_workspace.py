"""Enterprise V2 workspace API — DMS, court orders, knowledge, client ops."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.enterprise_workspace import (
    add_knowledge_entry,
    create_document_request,
    create_folder,
    ensure_enterprise_workspace_schema,
    ensure_matter_folders,
    get_court_order,
    get_document,
    list_audit,
    list_client_portal_ops,
    list_court_orders,
    list_documents,
    list_folders,
    request_client_review,
    search_court_orders,
    search_documents,
    search_knowledge,
    storage_summary,
    upload_court_order,
    upload_document,
    workspace_dashboard,
)

router = APIRouter(tags=["enterprise-workspace"])


class FolderCreate(BaseModel):
    practice_area: str = "Litigation"
    matter_id: str = ""
    folder_name: str = Field(..., min_length=1)
    parent_id: str = ""


class DocumentUpload(BaseModel):
    title: str = Field(..., min_length=1)
    filename: str = ""
    content_text: str = ""
    matter_id: str = ""
    folder_id: str = ""
    practice_area: str = "Litigation"
    doc_type: str = "General"
    tags: List[str] = Field(default_factory=list)


class OrderUpload(BaseModel):
    content_text: str = Field(..., min_length=20)
    filename: str = ""
    matter_id: str = ""
    client_name: str = ""
    order_type: str = "order"
    practice_area: str = "Litigation"
    run_analysis: bool = True


class KnowledgeCreate(BaseModel):
    entry_type: str = "memo"
    title: str = Field(..., min_length=2)
    content_text: str = ""
    practice_area: str = ""
    matter_id: str = ""
    court: str = ""
    tags: List[str] = Field(default_factory=list)


class DocRequestCreate(BaseModel):
    matter_id: str
    request_type: str = Field(..., min_length=2)
    client_email: str = ""
    notes: str = ""


class ApprovalRequestCreate(BaseModel):
    matter_id: str
    title: str = Field(..., min_length=2)
    draft_id: str = ""
    client_email: str = ""


@router.get("/dashboard")
def ent_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return workspace_dashboard(str(user["id"]), user)


@router.get("/search")
def ent_global_search(
    q: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.enterprise_hub import global_enterprise_search

    return global_enterprise_search(str(user["id"]), q)


@router.get("/matters")
def ent_matters_hub(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.enterprise_hub import list_matters_hub

    return {"matters": list_matters_hub(str(user["id"]))}


@router.get("/matters/{matter_id}/hub")
def ent_matter_hub(matter_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.enterprise_hub import get_matter_hub

    out = get_matter_hub(str(user["id"]), matter_id)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/analytics")
def ent_analytics(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.enterprise_hub import firm_analytics

    return firm_analytics(str(user["id"]))


@router.get("/folders")
def ent_folders(
    matter_id: str = "",
    practice_area: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {"folders": list_folders(str(user["id"]), matter_id=matter_id, practice_area=practice_area)}


@router.post("/folders")
def ent_folder_create(body: FolderCreate, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return create_folder(
        str(user["id"]),
        practice_area=body.practice_area,
        matter_id=body.matter_id,
        folder_name=body.folder_name,
        parent_id=body.parent_id,
    )


@router.post("/folders/seed-matter")
def ent_seed_matter_folders(
    matter_id: str = Query(...),
    matter_name: str = Query("Matter"),
    practice_area: str = Query("Litigation"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    ensure_matter_folders(str(user["id"]), matter_id, matter_name, practice_area)
    return {"ok": True, "folders": list_folders(str(user["id"]), matter_id=matter_id)}


@router.get("/documents")
def ent_documents(
    matter_id: str = "",
    folder_id: str = "",
    practice_area: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {
        "documents": list_documents(
            str(user["id"]),
            matter_id=matter_id,
            folder_id=folder_id,
            practice_area=practice_area,
        )
    }


@router.get("/documents/{doc_id}")
def ent_document_get(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    doc = get_document(str(user["id"]), doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/documents")
def ent_document_upload(body: DocumentUpload, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return upload_document(
        str(user["id"]),
        title=body.title,
        filename=body.filename,
        content_text=body.content_text,
        matter_id=body.matter_id,
        folder_id=body.folder_id,
        practice_area=body.practice_area,
        doc_type=body.doc_type,
        tags=body.tags,
        author=str(user.get("username") or user["id"]),
    )


@router.get("/documents/search")
def ent_document_search(
    q: str = "",
    matter_id: str = "",
    doc_type: str = "",
    tag: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {
        "results": search_documents(
            str(user["id"]), q, matter_id=matter_id, doc_type=doc_type, tag=tag
        )
    }


@router.get("/court-orders")
def ent_orders(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {"orders": list_court_orders(str(user["id"]), matter_id=matter_id)}


@router.get("/court-orders/{order_id}")
def ent_order_get(order_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    order = get_court_order(str(user["id"]), order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.post("/court-orders")
def ent_order_upload(body: OrderUpload, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return upload_court_order(
        str(user["id"]),
        content_text=body.content_text,
        filename=body.filename,
        matter_id=body.matter_id,
        client_name=body.client_name,
        order_type=body.order_type,
        practice_area=body.practice_area,
        run_analysis=body.run_analysis,
    )


@router.get("/court-orders/search")
def ent_order_search(
    q: str = "",
    judge: str = "",
    court: str = "",
    matter_id: str = "",
    order_type: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {
        "results": search_court_orders(
            str(user["id"]),
            q,
            judge=judge,
            court=court,
            matter_id=matter_id,
            order_type=order_type,
        )
    }


@router.get("/knowledge")
def ent_knowledge_search(
    q: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return {"results": search_knowledge(str(user["id"]), q)}


@router.post("/knowledge")
def ent_knowledge_create(body: KnowledgeCreate, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return add_knowledge_entry(
        str(user["id"]),
        entry_type=body.entry_type,
        title=body.title,
        content_text=body.content_text,
        practice_area=body.practice_area,
        matter_id=body.matter_id,
        court=body.court,
        tags=body.tags,
    )


@router.get("/client-portal")
def ent_client_portal(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return list_client_portal_ops(str(user["id"]))


@router.post("/client-portal/document-request")
def ent_doc_request(body: DocRequestCreate, user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return create_document_request(
        str(user["id"]),
        matter_id=body.matter_id,
        request_type=body.request_type,
        client_email=body.client_email,
        notes=body.notes,
    )


@router.post("/client-portal/request-review")
def ent_approval_request(
    body: ApprovalRequestCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_enterprise_workspace_schema()
    return request_client_review(
        str(user["id"]),
        matter_id=body.matter_id,
        title=body.title,
        draft_id=body.draft_id,
        client_email=body.client_email,
    )


@router.get("/audit")
def ent_audit(q: str = "", user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return {"entries": list_audit(str(user["id"]), query=q)}


@router.get("/storage")
def ent_storage(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_enterprise_workspace_schema()
    return storage_summary(str(user["id"]))
