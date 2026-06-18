from fastapi import APIRouter

from .endpoints import (
    account,
    admin,
    billing,
    chat,
    clauses,
    collab,
    crm,
    feedback,
    dashboard,
    drafting_studio,
    drafting_workspace,
    drafting_v3,
    drafting_v4,
    documents,
    ediscovery,
    enterprise,
    enterprise_workspace,
    engines,
    esign,
    health,
    ipc_bns_v3,
    legal_conversion,
    kb_debug,
    learning,
    matters,
    memory,
    orgs,
    portal,
    practice,
    research_log,
    saas_metrics,
    scim,
    sessions,
    speech,
    sso,
    subscriptions,
    templates,
    trust,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(ipc_bns_v3.router, prefix="/ipc-bns/v3")
api_router.include_router(legal_conversion.router, prefix="/legal-conversion")
api_router.include_router(chat.router, prefix="/chat")
api_router.include_router(engines.router, prefix="/engines")
api_router.include_router(documents.router, prefix="/documents")
api_router.include_router(kb_debug.router, prefix="/kb")
api_router.include_router(sessions.router, prefix="/sessions")
api_router.include_router(learning.router, prefix="/learning")
api_router.include_router(feedback.router, prefix="/feedback-learning")
api_router.include_router(scim.router, prefix="/scim/v2")
api_router.include_router(memory.router, prefix="/memory")
api_router.include_router(matters.router, prefix="/matters")
api_router.include_router(templates.router, prefix="/templates")
api_router.include_router(drafting_studio.router, prefix="/drafting")
api_router.include_router(drafting_workspace.router, prefix="/drafting")
api_router.include_router(drafting_v3.router, prefix="/drafting")
api_router.include_router(drafting_v4.router, prefix="/drafting")
api_router.include_router(clauses.router, prefix="/clauses")
api_router.include_router(billing.router, prefix="/billing")
# SaaS subscriptions (Stripe) — separate prefix to avoid route clashes with practice billing
api_router.include_router(subscriptions.router, prefix="/subscriptions")
api_router.include_router(orgs.router, prefix="/orgs")
api_router.include_router(sso.router, prefix="/sso")
api_router.include_router(enterprise.router, prefix="/enterprise")
api_router.include_router(enterprise_workspace.router, prefix="/enterprise/workspace")
api_router.include_router(account.router, prefix="/account")
api_router.include_router(admin.router, prefix="/admin")
api_router.include_router(trust.router, prefix="/trust")
api_router.include_router(crm.router, prefix="/crm")
api_router.include_router(collab.router, prefix="/collaboration")
api_router.include_router(portal.router, prefix="/portal")
api_router.include_router(esign.router, prefix="/esign")
api_router.include_router(ediscovery.router, prefix="/ediscovery")
api_router.include_router(research_log.router, prefix="/research")
api_router.include_router(practice.router, prefix="/practice")
api_router.include_router(dashboard.router, prefix="/dashboard")
api_router.include_router(saas_metrics.router, prefix="/saas-metrics")
api_router.include_router(speech.router, prefix="/speech")
