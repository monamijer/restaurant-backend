# API reference

Base path `/api/`. JSON everywhere except the PDF download. Authentication is
`Authorization: Bearer <access token>`. Roles: `client`, `staff`, `admin` (admin includes staff).

## Conventions

- **Pagination** (lists): `?page=2&page_size=50` (default 20, max 100). Response:
  `{count, next, previous, results}`. Categories and the settings are not paginated.
- **Filtering / search / ordering**: `?status=...`, `?search=...`, `?ordering=-created_at`.
- **Errors** (always): `{"success": false, "message": "...", "errors": {field: [..]}, "code": "..."}`
  with codes `VALIDATION_ERROR` (400), `AUTHENTICATION_FAILED` (401), `PERMISSION_DENIED` (403),
  `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `CONFLICT` (409), `THROTTLED` (429).
- **Money**: decimal strings (`"12.50"`), currency `USD`. Amounts are always computed by the server.
- **Times**: ISO 8601 in UTC. Reservations also expose the restaurant-local `date` and `time`.

## Authentication

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/register/` | anyone | Creates a `client`. Role cannot be chosen. |
| POST | `/auth/login/` | anyone | Returns `access`, `refresh`, `user`. |
| POST | `/auth/refresh/` | anyone | Rotates the refresh token. |
| POST | `/auth/logout/` | anyone | Blacklists the refresh token. |
| GET, PATCH | `/auth/me/` | signed in | Profile; role and email are read-only. |

## Catalogue and settings

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/settings/` | anyone | Name, timezone, hours, slot rules, tax, queue minutes. |
| PATCH | `/settings/` | admin | |
| GET | `/categories/`, `/categories/{id}/` | anyone | |
| POST, PUT, PATCH, DELETE | `/categories/` ... | admin | 409 if it still has dishes. |
| GET | `/menu-items/`, `/menu-items/{id}/` | anyone | Filters: `category`, `category_slug`, `is_available`, `is_featured`, `min_price`, `max_price`. |
| POST, PUT, PATCH, DELETE | `/menu-items/` ... | admin | Images: JPEG/PNG/WebP, 2 MB. 409 if ordered before. |
| POST | `/menu-items/{id}/set-availability/` | staff | `{is_available}` |
| GET | `/tables/`, `/tables/{id}/` | signed in | Filters: `status`, `min_capacity`, `location`. |
| POST, PUT, PATCH, DELETE | `/tables/` ... | admin | |
| POST | `/tables/{id}/set-status/` | staff | `{status}` |

## Reservations

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/reservations/availability/?date=&party_size=&duration_minutes=` | signed in | Free start slots with their tables. |
| POST | `/reservations/` | signed in | `{table, date, time, duration_minutes, party_size, notes}`; local date/time. 409 on overlap. |
| GET | `/reservations/`, `/reservations/{id}/` | signed in | Customers see their own. Filters: `status`, `table`, `date`. |
| POST | `/reservations/{id}/confirm/` `reject/` `complete/` `no-show/` | staff | |
| POST | `/reservations/{id}/cancel/` | owner (before start) or staff | |

A pending request holds its slot until `expires_at`, then becomes `expired`.

## Queue

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/queue/summary/` | anyone | `{waiting, estimated_wait_minutes}` |
| POST | `/queue/` | signed in | Customer: `{party_size, phone}`. Staff (walk-in): `{customer_name, phone, party_size}`. |
| GET | `/queue/`, `/queue/{id}/` | signed in | Customers see their own. Filters: `status`, `active`. Live `position`. |
| POST | `/queue/call-next/` | staff | First waiting ticket. |
| POST | `/queue/{id}/call/` `seat/` `no-show/` | staff | |
| POST | `/queue/{id}/cancel/` | owner or staff | |

## Orders, payments, invoices

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/orders/` | signed in | `{order_type, table, delivery_address, contact_phone, notes, items: [{menu_item, quantity, special_instructions}]}`. No prices: the server computes them. |
| GET | `/orders/`, `/orders/{id}/` | signed in | Customers see their own. Filters: `status`, `order_type`, `table`, `active`. |
| POST | `/orders/{id}/update-status/` | staff | `{status}`. Completing requires full payment. |
| POST | `/orders/{id}/cancel/` | owner (pending only) or staff | A paid order cannot be cancelled. |
| POST | `/payments/` | signed in | `{order, method, payment_token}`. Token required for card and mobile money; `tok_declined` is refused by the simulated gateway. A declined payment is returned with `status: "failed"`. |
| GET | `/payments/`, `/payments/{id}/` | signed in | Filters: `status`, `method`, `order`. |
| POST | `/payments/{id}/confirm/` | staff | Cash only. |
| POST | `/payments/{id}/cancel/` | owner or staff | Pending only. |
| GET | `/invoices/`, `/invoices/{id}/` | signed in | Issued automatically when an order is fully paid. |
| GET | `/invoices/{id}/download-pdf/` | owner or staff | `application/pdf`, never cached. |

## Notifications

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/notifications/` | signed in | Own only. Filters: `is_read`, `type`. Poll every 20 to 30 seconds. |
| GET | `/notifications/unread-count/` | signed in | |
| POST | `/notifications/{id}/mark-read/` | signed in | |
| POST | `/notifications/mark-all-read/` | signed in | |



## Accounts

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/change-password/` | signed in | `{old_password, new_password}`. Signs out other sessions; returns fresh `access` and `refresh`. |
| GET | `/users/`, `/users/{id}/` | staff | Staff only see customers; admins see everyone. Adds `orders_count`, `total_spent`, `last_order_at`. Filters: `role`, `is_active`; search by name, email, phone. |
| POST | `/users/` | admin | `{email, password, first_name, last_name, phone, address, role}`. |
| PATCH | `/users/{id}/` | admin | `first_name, last_name, phone, address, role, is_active`. 409 if it would remove the last or one's own admin access. Deactivating signs the user out. |
| POST | `/users/{id}/set-password/` | admin | `{password}`; 204. Signs the user out everywhere. |

There is no account deletion: deactivate instead.

## Dashboard and reports

Common query: `?start=YYYY-MM-DD&end=YYYY-MM-DD` (local days of the restaurant, default last 30 days,
at most 366), plus `group_by=day|week|month`, `limit=1..50` (top items) and `export=csv`
(never `format=csv`). Money is always a string. Lists include empty days, weeks or months.

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/dashboard/stats/` | staff | `kpis` (value, previous, change_percent), `today` (live tables, queue, orders, payments), `revenue_over_time`, `orders_over_time`, `top_items`, `recent_activity`. |
| GET | `/reports/revenue/` | admin | period, revenue, orders, average_order_value. |
| GET | `/reports/order-volume/` | admin | per period: total, dine_in, takeaway, delivery, cancelled. |
| GET | `/reports/top-items/` | admin | menu_item, name, quantity, revenue. |
| GET | `/reports/peak-hours/` | admin | 24 rows: hour, orders, revenue. |
| GET | `/reports/table-utilization/` | admin | per table: reservations, reserved_minutes, utilisation_percent, dine_in_orders, orders_value. |
| GET | `/reports/payments/?export=csv` | admin | Payment ledger, CSV only. |

CSV files start with a UTF-8 BOM for Excel, and any cell starting with `= + - @` is prefixed with `'`.


## Password reset

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/password-reset/` | anyone | `{email}`. Always answers 200 with the same message; 5 per hour. The e-mail links to `FRONTEND_URL/reset-password?uid=...&token=...`, valid one hour, single use. |
| POST | `/auth/password-reset/confirm/` | anyone | `{uid, token, new_password}`; 204. 400 with a `token` error for any bad link. Signs the user out everywhere. |

## Table QR codes

Each table has a QR code encoding `FRONTEND_URL/scan?t=<token>`. The frontend reads `t`, calls
`resolve-qr`, then lets the customer order on site with `table_token` set to that same value.

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/tables/resolve-qr/` | anyone | `{token}` returns `{id, number, capacity, location}`; 400 if invalid or replaced. |
| GET | `/tables/{id}/qr-code/` | admin | PNG, never cached. |
| GET | `/tables/qr-sheet/` | admin | A4 PDF with six codes per page. |
| POST | `/tables/{id}/regenerate-qr/` | admin | Invalidates every code already printed for the table. |

**Ordering on site** (`POST /orders/` with `order_type: "dine_in"`): customers send `table_token`
and may not send `table`; staff may send either. Tables no longer expose a `qr_code` field.