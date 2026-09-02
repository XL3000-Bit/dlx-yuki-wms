# Java v2 discovery record

This record was captured before the `/api/v2` implementation. It documents the current production contract rather than proposing schema changes.

## Runtime and routing

- FastAPI application: `backend/app/main.py`
- FastAPI API prefix: `/api/v1`
- FastAPI process port: `8000` (`START_DLX_WMS.bat` and the Vite proxy)
- Frontend development port: `5173`
- Existing Java application: Spring Boot 3.3.13 / Java 21, package `com.dlxyuki.wms`, currently containing legacy `/api/v1` experiments
- New split boundary: `/api/v2` on Java, default Java port `8081`; `/api/v1` remains on FastAPI

## Authentication contract

- Algorithm: HS256
- Shared secret environment variable: Python uses `JWT_SECRET_KEY`; Java v2 accepts `YUKI_JWT_SECRET` with `JWT_SECRET_KEY` as a compatibility fallback
- Access-token claims: `sub` (numeric user id encoded as a string), `type=access`, `jti`, `iat`, `exp`
- Authorization header: `Bearer <token>`
- The token does not contain username or role. Both implementations load the active user from `users` using `sub`; the database record supplies username, role, warehouse scope and customer scope.
- Missing credentials response: HTTP 401 with `{"detail":"Not authenticated"}`
- Invalid credentials response: HTTP 401 with `{"detail":"Invalid credentials"}`
- Java v2 does not expose login or refresh endpoints.

## Response and authorization behavior

- FastAPI success responses are raw JSON objects or arrays; there is no outer success envelope.
- Errors use FastAPI's `detail` JSON field.
- `ADMIN` or scope mode `ALL` can read all rows in that dimension.
- Scope mode `SELECTED` limits reads through `user_warehouses` / `user_customers`; an empty selected scope returns no scoped rows.
- Carrier and Amazon FC address lists require authentication but are not warehouse/customer scoped in the current FastAPI implementation.

## Existing tables used by Java v2

No table is created or altered.

- `users`, `user_warehouses`, `user_customers`: authentication identity and read scope
- `customers`: `id`, `customer_code`, `customer_name`, `contact_name`, `phone`, `email`, `remark`, `is_active`, timestamps
- `warehouses`: `id`, `warehouse_code`, `warehouse_name`, address fields, `is_active`, timestamps
- `carriers`: `id`, `carrier_code`, `carrier_name`, `scac`, contact fields, `remark`, `is_active`, timestamps
- `amazon_fc_addresses`: `id`, `fc_code`, `fc_name`, address fields, `is_active`, timestamps
- `inbound_records`: dashboard inbound counts; scoped by `warehouse_id` and `customer_id`
- `inventory_lots`: dashboard lot and available-quantity totals; scoped by `warehouse_id` and `customer_id`
- `outbound_orders`: dashboard outbound counts; scoped by `warehouse_id` and `customer_id`

## Existing-Java caveat

`backend-java` already contained legacy `/api/v1` controllers, including mutation-oriented experimental code, before this task. They are preserved to avoid destroying unrelated work. The v2 surface added by this task contains GET endpoints only, Nginx never routes `/api/v1` to Java, and the Java datasource is configured read-only as a defense-in-depth control.
