"""Create an isolated PostgreSQL cluster. Never starts/changes another project's service."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
BIN = Path(os.getenv("KCD_PG_BIN", "/opt/homebrew/opt/postgresql@18/bin"))
DATA = ROOT / "data" / "postgres"
ACCESS = ROOT / "data" / "database-access.json"


def main():
    DATA.parent.mkdir(exist_ok=True)
    if not ACCESS.exists():
        values = {"admin": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32),
                  "partner": secrets.token_urlsafe(15), "staff": secrets.token_urlsafe(15)}
        ACCESS.write_text(json.dumps(values))
        ACCESS.chmod(0o600)
    values = json.loads(ACCESS.read_text())
    if not (DATA / "PG_VERSION").exists():
        pw = ROOT / "data" / ".init-password"
        pw.write_text(values["admin"])
        pw.chmod(0o600)
        try:
            subprocess.run([str(BIN / "initdb"), "-D", str(DATA), "-U", "kcd_admin", "-E", "UTF8",
                            "--auth=scram-sha-256", "--pwfile", str(pw)], check=True, stdout=subprocess.DEVNULL)
        finally:
            pw.unlink(missing_ok=True)
    if subprocess.run([str(BIN / "pg_ctl"), "-D", str(DATA), "status"], stdout=subprocess.DEVNULL).returncode:
        socket = ROOT / "data" / "pg-socket"
        socket.mkdir(exist_ok=True)
        subprocess.run([str(BIN / "pg_ctl"), "-D", str(DATA), "-l", str(ROOT / "data" / "postgres.log"),
                        "-o", f"-p 5433 -h 127.0.0.1 -k {socket}", "start"], check=True)
    with psycopg.connect(host="127.0.0.1", port=5433, user="kcd_admin", password=values["admin"], dbname="postgres", autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='kcd_app'").fetchone():
            conn.execute(sql.SQL("CREATE ROLE kcd_app LOGIN PASSWORD {}").format(sql.Literal(values["app"])))
        for name in ("kcd_demo", "kcd_shop", "kcd_test"):
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER kcd_app").format(sql.Identifier(name)))
    env_path = BACKEND / ".env"
    existing = env_path.read_text().splitlines() if env_path.exists() else []
    base = f"postgresql+psycopg://kcd_app:{quote(values['app'])}@127.0.0.1:5433/"
    from cryptography.fernet import Fernet
    for name,value in {"KCD_DATABASE_URL":base+"kcd_demo","KCD_TEST_DATABASE_URL":base+"kcd_test","KCD_MODE":"demo",
                       "KCD_CUSTOMER_ENCRYPTION_KEYS":Fernet.generate_key().decode(),
                       "KCD_CUSTOMER_LOOKUP_KEY":secrets.token_hex(32)}.items():
        if not any(x.startswith(name+"=") for x in existing):existing.append(name+"="+value)
    env_path.write_text("\n".join(existing) + "\n")
    env_path.chmod(0o600)
    from app.infrastructure.database import engine_for
    from app.infrastructure.auth import create_user
    from sqlalchemy import select
    from app.infrastructure import database as db
    for name in ("kcd_demo", "kcd_shop", "kcd_test"):
        url = base + name
        subprocess.run([str(BACKEND / ".venv" / "bin" / "alembic"), "upgrade", "head"], cwd=BACKEND,
                       env={**os.environ, "KCD_DATABASE_URL": url}, check=True)
        engine = engine_for(url)
        for username, role in (("partner", "partner"), ("staff", "staff")):
            with engine.connect() as conn:
                exists = conn.execute(select(db.users.c.id).where(db.users.c.username == username)).first()
            if not exists:
                create_user(engine, username, values[username], role)
        engine.dispose()
    access = ROOT / "data" / "local-access.txt"
    access.write_text(f"Local demo login (keep private)\npartner: {values['partner']}\nstaff: {values['staff']}\n")
    access.chmod(0o600)
    print("Dedicated PostgreSQL cluster running on loopback:5433. Demo/shop/test migrated. Login details: data/local-access.txt")


if __name__ == "__main__":
    main()
