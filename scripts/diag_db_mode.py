import os
import sys
sys.path.insert(0, "/app")
from backend.app.core.database import connect_data_db, get_database_url, is_postgres
from backend.app.core.legacy_db import use_postgres_legacy

print("DATABASE_URL", (os.getenv("DATABASE_URL") or "")[:50])
print("LEGALEASE_DB_PATH", os.getenv("LEGALEASE_DB_PATH"))
print("SAAS_USE_POSTGRES_LEGACY", os.getenv("SAAS_USE_POSTGRES_LEGACY"))
print("is_postgres", is_postgres())
print("use_postgres_legacy", use_postgres_legacy())
conn = connect_data_db()
print("conn_type", type(conn).__name__)
try:
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print("users", n)
except Exception as e:
    print("users_err", e)
conn.close()
