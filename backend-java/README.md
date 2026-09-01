# DLX Yuki WMS Java backend — batches 1–2

Spring Boot 3.3 / Java 21 backend covering authentication, user administration, and master data. It reads the existing PostgreSQL schema and does not create, alter, or migrate database objects. The Python `backend/` remains unchanged.

## Requirements

- Java 21 (`java -version`)
- Maven 3.9+ (`mvn -version`)
- The existing PostgreSQL database

## Configuration

PowerShell example (use the same values as `backend/.env`):

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://dlx_user:password@localhost:5432/dlx_yuki_wms'
$env:JWT_SECRET_KEY = 'replace-with-the-same-secret-used-by-the-python-backend'
$env:JWT_ALGORITHM = 'HS256'
```

`DATABASE_URL` accepts the existing SQLAlchemy PostgreSQL form (`postgresql+psycopg://...`) as well as `postgresql://...`. Percent-encoded credentials are decoded. Defaults are documented in `src/main/resources/application.yml`; production-like use must set the real database password and JWT secret.

Optional settings: `ACCESS_TOKEN_EXPIRE_MINUTES` (default `30`), `REFRESH_TOKEN_EXPIRE_DAYS` (default `7`), and `PORT` (default `8000`). CORS allows `http://localhost:5173` and `http://127.0.0.1:5174`.

## Start

From `backend-java/`:

```powershell
mvn spring-boot:run
```

The service listens on port **8000** by default. Check it with:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Run tests with `mvn -q test`. Login is `POST /api/v1/auth/login`; protected requests use `Authorization: Bearer <access_token>`.

Implemented compatibility areas:

- Authentication: `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/users/me`
- User administration: `/api/v1/users`, `/api/v1/users/bootstrap`, and `/api/v1/users/{id}` (including `/{id}/scope`)
- Master data: `/api/v1/master-data/customers`, `warehouses`, `warehouse-areas`, `warehouse-locations`, `carriers`, and `amazon-fc-addresses`

Inbound, inventory, FBA, scan, and dashboard APIs are intentionally not part of batch 2. Keep the frontend proxy on the Python backend for daily warehouse operations until those batches are accepted.
