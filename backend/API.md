# API contract

Base `/api`. Public products GET returns an array with id/name_zh/name_en/material_zh/material_en/description_zh/description_en/category/sample. Product GET by id returns an object. All lists are arrays. All errors use `{detail: string | validation[]}`. CRM requests require `Authorization: Bearer <token>`; do not put token in a URL.

- POST auth/login `{username,password}` → `{token, token_type, expires_in,user}`. POST auth/logout revokes current token.
- POST inquiries `{company,contact_name,channel,locale:'zh'|'en',product_id?:number,quantity?:number,width?:number,height?:number,unit?:'mm'|'inch',expected_date?:string,notes?:string,submission_key?:string}` → `{id,reference,status}`. Reuse the key only for retries of the same submission. Dimensions and date may be omitted.
- POST conversations `{company?,contact_name,channel,locale,weekday_slot,notes?,submission_key?}` → same receipt. Does not book a calendar.
- GET inquiries → full inquiries including followups; GET inquiries/{id}. GET customers includes contacts.
- POST followups `{inquiry_id,note,next_at:'ISO date time'|''}`. New inquiry becomes contacted.
- GET dashboard → new_inquiries/customers/quotes/active_orders/followups.
- POST quotes `{inquiry_id,locale,currency:'NZD',valid_until:'YYYY-MM-DD',discount:0,shipping:0,tax:0,terms,lines:[{product_id,width,height,unit,material,color,control,quantity,unit_price}]}` → quote object with versions[]. Prices demonstration only; NZD is an example, not confirmed currency.
- GET quotes and GET quotes/{id} → quote(s) with versions. Each immutable version includes quote_id/version/lines/subtotal/discount/shipping/tax/total/created_at/accepted_order_id. Money is a two-decimal string.
- POST quotes/{id}/versions same body → new immutable version (not quote wrapper).
- GET quotes/{id}/versions/{n}/export?lang=zh|en → HTML. Fetch with bearer then display returned HTML in a window; browser print supports PDF. Never put bearer in query params.
- POST quotes/{id}/versions/{n}/accept `{note}` → order. Only latest valid version can be accepted; one order per quote, retry same version is idempotent.
- GET orders and GET orders/{id} → order(s) with snapshot and history. Snapshot includes accepted quote version plus customer and confirmation note.
- POST orders/{id}/status `{status:'confirmed'|'production'|'ready'|'delivered',note?}` → order. Advance one step; no arbitrary backward jump.

SQLite database defaults backend/vera.db; set VERA_DB to use another file. Demo single admin user. No production deployment, multiuser permissions, automated email, pricing, inventory or payment integrations are claimed.


## Product maintenance (local demo)
- `GET /api/admin/products`: signed-in staff/admin can view the full catalogue including hidden products.
- `POST /api/admin/products`: administrator creates a product. `POST /api/admin/products/{id}` updates it. Fields: bilingual name/material/description, category, sample, published, image_url, unit, optional width_min/max and height_min/max, colors[], controls[]. Positive ranges, min <= max. New products default hidden.
- `POST /api/admin/product-images`: administrator uploads JSON `{data: base64, content_type: image/png|image/jpeg|image/webp}`. Maximum decoded size 5 MB. Validates encoding/type signature; responds with local image_url. Images persist under backend/media (VERA_MEDIA_DIR can override); include this directory with database backups.
- Public `/api/products` and `/api/products/{id}` return published catalogue entries; hidden details return404. The website uses image_url and the same product IDs.
- Product changes do not modify immutable quote versions or order snapshots. Admin authorization is enforced by the server; staff write attempts return403.
- `python test_products.py` runs in temporary database/media directories.
