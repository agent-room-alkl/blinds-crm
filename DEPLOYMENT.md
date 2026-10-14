# Vercel deployment of the VERA demo

The repository contains a Vue/Vite frontend and FastAPI backend. Select **Services**, root directory `./`, not a single backend-only project. The root vercel.json routes `/api/*` to backend and all other requests to frontend; the service receives the original `/api/*` path. Backend entry is backend/index.py. Frontend builds with npm run build to dist; frontend/vercel.json supports direct SPA navigation.

## Persistent data and server-only variables

Set these in Vercel runtime environment variables, using the existing provider values without exposing them in a room or source:
- DATABASE_URL or POSTGRES_URL (provider pooler allowed; server strips ORM-only flags and disables prepared statements).
- VERA_DB_SCHEMA=vera; VERA_DB_BACKEND=postgres; VERA_AUTO_INIT=0.
- R2_ENDPOINT, R2_BUCKET, R2_ACCESS_ID and R2_ACCESS_KEY for the private product-image bucket.
- VERA_STORAGE_BACKEND=r2.
Do not prefix a database credential or storage key with VITE_. No backend secret is bundled into frontend.

The shared PostgreSQL business schema is isolated by SET LOCAL search_path and all transactions target vera. Migration created it only if absent. There is no automatic schema creation on cloud cold starts. New installation: explicitly run backend/init_database.py with VERA_DEMO_PASSWORD set; migration of an existing local demo preserves users/password hashes and skips old sessions. Change the demonstration password through CRM before publishing access.

Product uploads use the private R2 bucket named by the host. Objects stay private: an unsigned storage URL is rejected, and the app serves published images through /api/media. Signed-in staff can preview hidden uploads. Cloud server uploads are limited to 3MB per image; local uploads allow 5MB. Static original sample illustrations stay bundled with the frontend. Set VERA_STORAGE_BACKEND=local to keep a machine on local files.

## Migration already performed locally

The migration script refuses any existing target schema, backs up the local SQLite source, inserts into the new schema in one transaction, resets ID sequences, and compares quote/version/order snapshot text byte-for-byte. Old sessions are deliberately excluded. Never rerun it to overwrite a schema. Keep local `.env`, SQLite files/backups, runtime uploaded media and dependencies out of Git.

## Checks

- `python backend/test_api.py` / `python backend/test_products.py`: forced isolated local SQLite suites, even if .env has live PostgreSQL settings.
- `python backend/test_postgres.py`: actual PostgreSQL suites in unique disposable vera_test_* schemas, then removes those test schemas only. Covers main workflow, products/gallery/hidden-image privacy and concurrent retries/versions/order acceptance.
- `python backend/test_storage_r2.py`: private R2 upload/read smoke, unsigned read rejected, then removes only its own unique tiny test object.
- `npm --prefix frontend run build`.

A Vercel cloud deployment has not been performed by the agent merely by preparing this configuration. After deploying, check /api/health (database:postgres), sign in, products/thumbnail switching, one test inquiry, quote revision/acceptance and image upload. Monitor actual logs; do not paste secrets into them or the room.

References: https://vercel.com/kb/guide/vercel-services ; https://vercel.com/docs/frameworks/backend/fastapi ; https://developers.cloudflare.com/r2/api/s3/api/ ; https://www.psycopg.org/psycopg3/docs/advanced/pool.html

## Optional SMTP replies
Set SMTP_HOST, SMTP_PORT (587), SMTP_SECURITY=starttls, SMTP_FROM, SMTP_USERNAME and SMTP_PASSWORD in the backend runtime environment. For implicit TLS use SMTP_SECURITY=ssl and port465. Use the provider's application password where required. TLS certificate verification stays enabled. Local server reads the same keys from the gitignored .env; restart after configuration changes. Keep passwords out of VITE_ variables, repository files and room transcripts.
The inquiry email composer stays disabled until a host and valid sending address are configured. Delivery tests mock the provider; live delivery has not been verified without a real mailbox configuration. No automatic messages are sent when an inquiry is submitted.
