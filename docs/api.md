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