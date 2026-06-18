# LegalEase.AI — SOC2 / ISO 27001 Readiness Mapping (Draft)

This document maps existing controls to common audit frameworks. **Not a certification.**

## Control mapping

| Control area | LegalEase implementation | Status |
|--------------|-------------------------|--------|
| Access control | JWT, RBAC, org isolation, superadmin gate | Implemented |
| Encryption in transit | TLS via nginx; `FORCE_HTTPS=1` | Config at deploy |
| Encryption at rest | bcrypt passwords; optional `DATA_ENCRYPTION_KEY` Fernet | Partial |
| Audit logging | `audit_service` — login, upload, billing, admin | Implemented |
| Data export / deletion | GDPR ZIP export; `DELETE /account` | Implemented |
| Change management | Git + CI (`ci.yml`), Alembic migrations | Implemented |
| Monitoring | Sentry, `/api/v1/metrics`, structured logs | Partial |
| Vendor management | Stripe, Gemini, SendGrid — DPAs required at enterprise | Planned |
| Penetration testing | Annual third-party test recommended | Not started |

## Next steps for SOC2 Type II

1. Appoint security owner and document policies (access, incident response, backup).
2. Enable production checklist items (TLS, secrets rotation, backup drills).
3. Run tenant isolation attack tests in CI quarterly.
4. Engage auditor after 3 months of control evidence collection.

See also [SECURITY.md](../SECURITY.md) and [RISK_REGISTER.md](RISK_REGISTER.md).
