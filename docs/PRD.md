# LegalEase.AI — Product Requirements Document (PRD)

## Roles & user stories

### Lawyer
- As a lawyer, I want to upload case documents so that the knowledge base can answer grounded questions.
- As a lawyer, I want to create matters and scope AI to matter evidence so that answers stay case-specific.
- As a lawyer, I want to share a client portal link so that clients can track progress without full login.
- As a lawyer, I want to bill time and generate invoices so that firm revenue is captured in one system.

### Client (portal)
- As a client, I want to view matter status and timeline so that I know case progress.
- As a client, I want to upload requested documents so that my lawyer receives them securely.
- As a client, I want to sign documents electronically so that filings are not delayed.

### Firm owner / Admin
- As a firm owner, I want to invite team members and enforce seat limits so that billing matches usage.
- As a firm owner, I want subscription self-service (Stripe) so that upgrades do not require support tickets.
- As an admin, I want audit logs and usage metrics so that compliance and growth can be monitored.

### Paralegal
- As a paralegal, I want matter tasks and e-discovery triage so that lawyers focus on strategy.
- As a paralegal, I want CRM intake Kanban so that leads convert to matters consistently.

## Acceptance criteria (MVP+)

| Feature | Criteria |
|---------|----------|
| KB chat | Answers cite sources; NOT_FOUND when confidence below threshold |
| Matter AI | `matter_only` mode queries matter FAISS index, not global KB |
| Multi-tenant | Firm A cannot read Firm B matters, docs, or vectors |
| Billing | Stripe webhook updates plan within 60s; Hybrid blocked on Free |
| Portal | Token URL read-only; upload requires valid token + matter scope |

## Out of scope (Phase 3+)

- Messenger-style E2E encryption (incompatible with server-side RAG)
- Native mobile apps (PWA/responsive web first)
- Live court API sync (roadmap Phase 6)
