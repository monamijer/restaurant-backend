# Maintenance backlog

Deliberately postponed. Each item says why it is acceptable now and what triggers the work.

## After the project is complete

| Item | Current behaviour | Why it is acceptable now | Work needed |
|---|---|---|---|
| Menu translation | Dish names, descriptions and categories have one language (French in the demo data) | The interface is bilingual through vue-i18n; the menu is content, edited by the restaurant | Translated fields on `Category` and `MenuItem` (migration), serializers that pick the requested language |
| Notification translation | Messages are stored and shown in English | Messages are short and informational | Store a notification code plus parameters, render them in the interface language (migration) |
| Automatic `reserved` table status | Set by hand | Availability for bookings is computed from reservations, not from this flag | A rule such as "reserved within the next hour" evaluated by a scheduled job |
| Refunds and credit notes | A paid order cannot be cancelled | Prevents an inconsistent state; no refund flow is required by the specification | Refund through the gateway, credit-note numbering |
| Split or partial payments | One payment covers the order total | Matches the specification | Allow several payments per order with a balance |

## At deployment

- Replace every development secret: `SECRET_KEY`, database user and password, the demo
  administrator password. Print the table QR codes only after the final `SECRET_KEY` is set.
- Set `DEBUG=False`, real `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`, and a real `FRONTEND_URL`.
- Configure a real SMTP server (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `DEFAULT_FROM_EMAIL`), otherwise password reset e-mails will not arrive.
- Replace the simulated payment gateway with a real provider, or keep it for a demo with
  `ALLOW_SIMULATED_PAYMENTS=True`.
- Use a shared cache (Redis or database) for throttling, and run `flushexpiredtokens` and
  `expire_reservations` on a schedule.
- Never run `seed_demo` in production.