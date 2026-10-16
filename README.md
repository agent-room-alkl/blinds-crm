# VERA Shading Solutions

## Customer portal and project-order prototype (2026-10-16)

`/portal` uses a separate customer login provisioned by a staff administrator in CRM → Project orders. The CRM now opens on project operations; the previous inquiry/quotation/mail workflow remains under History. Customers can submit named window configurations for review, and staff can record the **60%** deposit, supplier reference, transit, partial arrivals and deliveries. Actual arrival quantities drive email notifications with explicit delivery status and retry boundaries.

This is a local workflow prototype. The supplied workbook requires both area and width/drop-matrix pricing, product-dependent options, installation minimums, GST and ROUNDUP rules. Those commercial rules and the supplier template have **not** been imported. Unconfigured prices stay empty and block invoice acceptance. The website's five shutter series are mapped in the review documents; the existing sample catalogue has not been silently replaced. Monthly rebate calculation, partial-arrival billing, confirmed invoice layout and profile editing remain follow-up work. Dashboard figures are labelled examples.

Existing databases need the additive `python backend/migrate_workflow.py` migration during deployment; this change does not run it against a live database. See [API and limitations](backend/OPERATIONS.md), [implementation plan](docs/CRM-implementation-plan.zh-CN.md), [client email/workbook review](docs/CRM-source-review.zh-CN.md) and [catalogue mapping](docs/CRM-catalog-mapping.zh-CN.md).

Validation: `python backend/test_operations.py`, `python backend/test_api.py`, `python backend/test_workflow.py`, `python backend/test_products.py`, and `npm run build` in `frontend`. Backend checks use isolated databases and mocked external services.

中英双语批发官网与客户订单 CRM 的本地演示。演示账号（CRM 登录由 T-03 实现）：`dylan` / `vera-demo`。

## 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：`http://127.0.0.1:8000/api/health` 返回包含 `status: "ok"` 的JSON。

## 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。右上角语言按钮只改文案，不改变当前路由。

内部 CRM：`http://localhost:5173/crm`，账号 `dylan` / `vera-demo`。未登录看不到客户资料。

跑后端测试前先在虚拟环境安装 `httpx2`，然后在 `backend` 目录执行 `python test_api.py`。


## Current demo workflows
- A website inquiry creates customer details and an inquiry. CRM → Quotations → latest version → Customer accepted → record acceptance evidence → Create order. External phone/email orders can also be recorded directly in Orders → Record an order. Existing orders link back to their quote version; revisions never change frozen orders.
- Products: administrators manage bilingual details, dimension ranges, options and local images. Sales users can view them. Published products share the same API and IDs with the website; hidden products are excluded.
- Product image uploads persist in `backend/media/`; back this directory up with the SQLite database. Both contain local state and are excluded from Git.
- GPT-5 drafts editable email content and summarizes archived communication when configured. Raw mail is retained if analysis fails or is unconfigured. Sending still requires an explicit Send email action.
- Sample company contacts, photos and prices are demonstrative. Replace them with confirmed company/product information before any real publication. This project is a local demo, not a production deployment.
- Independent product checks: `python backend/test_products.py`. Main workflow checks: `python backend/test_api.py`.
- Optional acceptance walkthrough: with the backend running, `python backend/seed_review_quote.py` adds an idempotent unaccepted demonstration quote without creating an order.


## Shared PostgreSQL and cloud deployment

Server loads backend/.env, then root .env (environment variables take precedence). With DATABASE_URL/POSTGRES_URL configured, it uses the isolated vera PostgreSQL schema; without configuration it retains the local SQLite demo. Cloud product images use the private Cloudflare R2 bucket. See DEPLOYMENT.md and backend/.env.example. PostgreSQL migration preserves existing users but not old sessions; sign in again after switching. Cloud deployment needs Services root ./ and the server variables described in DEPLOYMENT.md.

## CRM editing and communication
Quotation editing presents conditions, specifications and charges on one page. Incomplete drafts persist and can be resumed; finalizing validates all fields. Each project has one conversation timeline, automatic summaries and follow-up tasks, rather than duplicate manual communication forms. Direct orders record customer/source/reference, manually priced specifications and acceptance evidence without creating a fake quotation; retrying the same submission does not duplicate it.
Optional SMTP settings and deployment setup are documented in DEPLOYMENT.md. Email is sent only by clicking Send email; the provider must first be configured server-side. Tests use a mocked mail server and send no real messages.


## Automated project communication
Local configuration lives in the ignored root `.env`; use `backend/.env.example` for a safe template. Set `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5`, SMTP and IMAP credentials only on the server. Missing credentials are shown honestly in Settings. Existing databases need `python backend/migrate_workflow.py` before starting this revision. Run `python backend/test_workflow.py` for isolated draft/mail/AI contract checks; it makes no real mail or model calls. See DEPLOYMENT.md for the scheduled inbox collector and webhook.


## Keep the local preview running
From the repository root, use two PowerShell terminals: `./dev.ps1 backend` and `./dev.ps1 frontend`. Keep both terminals open; Ctrl+C stops the corresponding service. Open http://127.0.0.1:5173/crm. This pair explicitly connects the frontend to port 8002, avoiding a stale older backend on 8000. If the port is already occupied, keep the existing current service or stop it from its own terminal before starting another; the script does not terminate unrelated processes.
