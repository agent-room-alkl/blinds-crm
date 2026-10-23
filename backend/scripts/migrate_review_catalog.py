"""Copy the reviewed catalog into PostgreSQL without orders.

Default is a read-only dry run. It never prints the database URL or password
hashes. --apply is refused until a backup file exists and --confirm matches.
This task does not run --apply.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlencode, urlunsplit

# Wholesale Customer columns A and D. Curtain Plus and Promax Colours are not on that sheet.
WHOLESALE = {
    "auckland shutters": "AA",
    "cathers furniture": "CF",
    "funina ltd": "FL",
    "goregous curtains": "GC",
    "interior studio": "IS",
    "mblinds": "MB",
    "nz blinds and awnings": "NZBA",
    "rhino blinds": "RB",
    "rollerflex": "RF",
    "soho blinds": "SH",
    "impact blinds": "IB",
    "the shutter shack ltd": "SK",
    "window art ltd": "WA",
    "amy curtains": "AM",
    "elitra shading": "ES",
    "vlad": "VL",
    "umi curtain": "UC",
}
EXCLUDED = {"curtain plus", "promax colours"}
PRODUCT_CODES = {
    "Shutters_PVC",
    "Shutters_PVC_Eco",
    "Shutters_Pinewood",
    "Shutters_Basswood",
    "VERA_Ashwood_provisional",
}
CONFIRM = "KEEP-ORDERS-AND-REPLACE-CATALOG"
SKIPPED_KINDS = {"project", "invoice", "rebate", "notification", "shipment", "batch", "fulfilment"}


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def load_plan(source: Path):
    db = sqlite3.connect(source)
    db.row_factory = sqlite3.Row
    customers = []
    for row in db.execute("SELECT id, company, locale, notes FROM customers ORDER BY id"):
        company = (row["company"] or "").strip()
        key = company.casefold()
        if key in EXCLUDED or key not in WHOLESALE:
            continue
        profile = db.execute("SELECT username, data FROM portal_profiles WHERE customer_id=?", (row["id"],)).fetchone()
        if not profile:
            raise SystemExit(f"Missing portal profile for {company}")
        data = json.loads(profile["data"])
        code = (data.get("customer_code") or "").strip()
        if code != WHOLESALE[key] or data.get("customer_type") != "wholesale":
            raise SystemExit(f"Customer {company} is not wholesale {WHOLESALE[key]}")
        data = {**data, "customer_type": "wholesale", "customer_code": code, "portal_login": "disabled"}
        customers.append({
            "company": company,
            "locale": row["locale"],
            "notes": row["notes"] or "",
            "username": profile["username"],
            "data": data,
        })
    if len(customers) != 17:
        raise SystemExit(f"Expected 17 wholesale customers, found {len(customers)}")
    products = []
    for row in db.execute("SELECT id, data FROM products ORDER BY id"):
        item = json.loads(row["data"])
        if item.get("source_code") in PRODUCT_CODES:
            products.append({"source_code": item["source_code"], "data": item})
    if len(products) != 5:
        raise SystemExit(f"Expected 5 VERA products, found {len(products)}")
    providers = [dict(row) for row in db.execute("SELECT name, contact_email, notes, active, created_at FROM providers ORDER BY id")]
    templates = [dict(row) for row in db.execute(
        "SELECT p.name AS provider_name, t.name, t.sheet_name, t.column_mappings, t.active, t.created_at "
        "FROM provider_templates t JOIN providers p ON p.id=t.provider_id ORDER BY t.id")]
    pointer = db.execute("SELECT data FROM operations_records WHERE id='template-current'").fetchone()
    if not pointer:
        raise SystemExit("Missing template-current")
    pointer_data = json.loads(pointer["data"])
    template_id = pointer_data.get("template_id") or ""
    if not str(template_id).startswith("template:52abc3"):
        raise SystemExit("Current pricing template is not version 52abc3")
    template = db.execute("SELECT id, kind, data FROM operations_records WHERE id=?", (template_id,)).fetchone()
    if not template:
        raise SystemExit("Current pricing template row is missing")
    knowledge = json.loads(template["data"])
    if not knowledge.get("knowledge_published"):
        raise SystemExit("Pricing template 52abc3 is not published")
    db.close()
    return {
        "customers": customers,
        "products": products,
        "providers": providers,
        "provider_templates": templates,
        "template_id": template["id"],
        "template_kind": template["kind"],
        "template": knowledge,
        "pointer": pointer_data,
    }


def database_url():
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRES_URL_NON_POOLING") or ""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
        return ""
    allowed = {"sslmode", "connect_timeout", "application_name", "channel_binding", "options"}
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if key in allowed])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def read_only_connection(url, schema):
    import psycopg
    conn = psycopg.connect(url, autocommit=False)
    conn.execute("SET default_transaction_read_only = on")
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SELECT set_config('search_path', %s, true)", (schema,))
    return conn


def table_count(conn, table):
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=%s",
        (table,),
    ).fetchone()
    if not row or row[0] == 0:
        return None
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def kind_counts(conn):
    if table_count(conn, "operations_records") is None:
        return {}
    return {kind: count for kind, count in conn.execute("SELECT kind, COUNT(*) FROM operations_records GROUP BY kind")}


def target_snapshot(conn):
    counts = {name: table_count(conn, name) for name in (
        "customers", "products", "providers", "provider_templates", "users", "portal_profiles")}
    kinds = kind_counts(conn)
    companies = []
    if counts["customers"]:
        companies = [row[0] for row in conn.execute("SELECT company FROM customers")]
    codes = set()
    if counts["products"]:
        for (data,) in conn.execute("SELECT data FROM products"):
            try:
                codes.add(json.loads(data).get("source_code"))
            except json.JSONDecodeError:
                continue
    provider_names = []
    if counts["providers"]:
        provider_names = [row[0] for row in conn.execute("SELECT name FROM providers")]
    template_ids = set()
    if kinds:
        template_ids = {row[0] for row in conn.execute("SELECT id FROM operations_records WHERE kind='template'")}
    return {"counts": counts, "kinds": kinds, "companies": companies, "product_codes": codes,
            "provider_names": provider_names, "template_ids": template_ids}


def project(plan, snap):
    companies = {str(name).casefold() for name in snap["companies"]}
    new_customers = [row for row in plan["customers"] if row["company"].casefold() not in companies]
    new_products = [row for row in plan["products"] if row["source_code"] not in snap["product_codes"]]
    names = {str(name).casefold() for name in snap["provider_names"]}
    new_providers = [row for row in plan["providers"] if row["name"].casefold() not in names]
    current_customers = snap["counts"]["customers"] or 0
    current_products = snap["counts"]["products"] or 0
    current_providers = snap["counts"]["providers"] or 0
    orders = snap["kinds"].get("project", 0)
    invoices = snap["kinds"].get("invoice", 0)
    return {
        "orders_now": orders,
        "orders_after": orders,
        "invoices_now": invoices,
        "invoices_after": invoices,
        "customers_now": current_customers,
        "customers_after": current_customers + len(new_customers),
        "products_now": current_products,
        "products_after": current_products + len(new_products),
        "providers_now": current_providers,
        "providers_after": current_providers + len(new_providers),
        "provider_templates_now": snap["counts"]["provider_templates"] or 0,
        "provider_templates_after": (snap["counts"]["provider_templates"] or 0) + len(plan["provider_templates"]),
        "pricing_version_present": plan["template_id"] in snap["template_ids"],
        "users_now": snap["counts"]["users"],
        "users_after": snap["counts"]["users"],
        "customers_already_present": len(plan["customers"]) - len(new_customers),
    }


def report(plan, projected):
    print("dry-run only; no production rows written")
    print(f"source customers {len(plan['customers'])} products {len(plan['products'])} providers {len(plan['providers'])} provider_templates {len(plan['provider_templates'])}")
    print(f"pricing template {plan['template_id'][:20]} published")
    print("skipped: orders invoices rebates notifications shipments staff users portal sessions")
    for key in (
        "orders_now", "orders_after", "invoices_now", "invoices_after",
        "customers_now", "customers_after", "products_now", "products_after",
        "providers_now", "providers_after", "provider_templates_now", "provider_templates_after",
    ):
        print(f"{key} {projected[key]}")
    print(f"pricing_version_already_present {projected['pricing_version_present']}")
    print(f"customers_already_present {projected['customers_already_present']}")
    print("apply would replace those existing portal password hashes and mark the accounts disabled")
    print(f"staff_users_unchanged {projected['users_now']}")
    print("portal accounts disabled, demo passwords not copied:")
    for row in plan["customers"]:
        print(f"  {row['username']} {row['company']} {row['data']['customer_code']} disabled")


def backup_database(url, schema, destination: Path):
    pg_dump = shutil.which("pg_dump")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if pg_dump:
        completed = subprocess.run(
            [pg_dump, "--schema", schema, "--file", str(destination.with_suffix(".sql")), url],
            check=False, capture_output=True, text=True,
        )
        if completed.returncode != 0:
            raise SystemExit("pg_dump failed; production was not changed")
        print("backup", destination.with_suffix(".sql").name)
        return
    import psycopg
    with psycopg.connect(url) as conn:
        conn.execute("SET default_transaction_read_only = on")
        conn.execute("SELECT set_config('search_path', %s, true)", (schema,))
        payload = {"schema": schema, "taken_at": datetime.now().isoformat(timespec="seconds")}
        for table in ("customers", "products", "providers", "provider_templates", "portal_profiles", "operations_records", "users"):
            present = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=%s",
                (table,),
            ).fetchone()[0]
            payload[table] = [] if not present else [list(row) for row in conn.execute(f"SELECT * FROM {table}")]
        destination.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    print("backup", destination.name)


def apply_plan(url, schema, plan, backup_dir: Path):
    import psycopg
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_database(url, schema, backup_dir / f"vera-production-{stamp}.json")
    with psycopg.connect(url) as conn:
        conn.execute("SELECT set_config('search_path', %s, true)", (schema,))
        for row in plan["customers"]:
            found = conn.execute("SELECT id FROM customers WHERE lower(company)=lower(%s)", (row["company"],)).fetchone()
            stored = password_hash(secrets.token_urlsafe(24))
            payload = json.dumps(row["data"], ensure_ascii=False)
            if found:
                cid = found[0]
                conn.execute(
                    "UPDATE portal_profiles SET password_hash=%s, data=%s WHERE customer_id=%s",
                    (stored, payload, cid),
                )
            else:
                cid = conn.execute(
                    "INSERT INTO customers(company, locale, notes) VALUES(%s, %s, %s) RETURNING id",
                    (row["company"], row["locale"], row["notes"]),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO portal_profiles(customer_id, username, password_hash, data) VALUES(%s, %s, %s, %s)",
                    (cid, row["username"], stored, payload),
                )
        for row in plan["products"]:
            body = json.dumps(row["data"], ensure_ascii=False)
            matches = []
            for pid, data in conn.execute("SELECT id, data FROM products"):
                try:
                    if json.loads(data).get("source_code") == row["source_code"]:
                        matches.append(pid)
                except json.JSONDecodeError:
                    continue
            if matches:
                conn.execute("UPDATE products SET data=%s WHERE id=%s", (body, matches[0]))
            else:
                conn.execute("INSERT INTO products(data) VALUES(%s)", (body,))
        for row in plan["providers"]:
            found = conn.execute("SELECT id FROM providers WHERE lower(name)=lower(%s)", (row["name"],)).fetchone()
            if found:
                conn.execute(
                    "UPDATE providers SET contact_email=%s, notes=%s, active=%s WHERE id=%s",
                    (row["contact_email"], row["notes"], row["active"], found[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO providers(name, contact_email, notes, active, created_at) VALUES(%s, %s, %s, %s, %s)",
                    (row["name"], row["contact_email"], row["notes"], row["active"], row["created_at"]),
                )
        conn.execute(
            "INSERT INTO operations_records(id, kind, customer_id, data) VALUES(%s, %s, NULL, %s) "
            "ON CONFLICT(id) DO UPDATE SET kind=EXCLUDED.kind, data=EXCLUDED.data",
            (plan["template_id"], plan["template_kind"], json.dumps(plan["template"], ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO operations_records(id, kind, customer_id, data) VALUES('template-current', 'template_pointer', NULL, %s) "
            "ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data",
            (json.dumps(plan["pointer"], ensure_ascii=False),),
        )
        conn.commit()
    print("apply finished; orders were not modified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "vera-review.db")
    parser.add_argument("--schema", default=os.getenv("VERA_DB_SCHEMA", "vera"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--backup-dir", type=Path, default=Path(os.environ.get("TEMP", ".")) / "vera-production-backups")
    args = parser.parse_args()
    if not args.schema.isidentifier() or args.schema in {"public", "information_schema"}:
        raise SystemExit("Refusing schema name")
    plan = load_plan(args.source)
    url = database_url()
    if not url:
        raise SystemExit("DATABASE_URL is not set; production was not contacted")
    if args.apply:
        if args.confirm != CONFIRM:
            raise SystemExit("Refusing to write. Pass --confirm " + CONFIRM)
        apply_plan(url, args.schema, plan, args.backup_dir)
        return
    conn = read_only_connection(url, args.schema)
    try:
        snap = target_snapshot(conn)
        conn.rollback()
    finally:
        conn.close()
    report(plan, project(plan, snap))


if __name__ == "__main__":
    main()
