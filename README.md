# VERA Shading Solutions

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
- A website inquiry creates customer details and an inquiry. CRM → Quotations → latest version → Customer accepted → record acceptance evidence → Create order. Existing orders link back to their quote version; revisions never change frozen orders.
- Products: administrators manage bilingual details, dimension ranges, options and local images. Sales users can view them. Published products share the same API and IDs with the website; hidden products are excluded.
- Product image uploads persist in `backend/media/`; back this directory up with the SQLite database. Both contain local state and are excluded from Git.
- Assistant drafts currently use deterministic rules. No external AI model is connected. Draft generation does not send messages or persist follow-ups automatically.
- Sample company contacts, photos and prices are demonstrative. Replace them with confirmed company/product information before any real publication. This project is a local demo, not a production deployment.
- Independent product checks: `python backend/test_products.py`. Main workflow checks: `python backend/test_api.py`.
- Optional acceptance walkthrough: with the backend running, `python backend/seed_review_quote.py` adds an idempotent unaccepted demonstration quote without creating an order.


## Shared PostgreSQL and cloud deployment

Server loads backend/.env, then root .env (environment variables take precedence). With DATABASE_URL/POSTGRES_URL configured, it uses the isolated vera PostgreSQL schema; without configuration it retains the local SQLite demo. Cloud product images use the private Cloudflare R2 bucket. See DEPLOYMENT.md and backend/.env.example. PostgreSQL migration preserves existing users but not old sessions; sign in again after switching. Cloud deployment needs Services root ./ and the server variables described in DEPLOYMENT.md.
