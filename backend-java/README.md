# Yuki WMS Java read-only backend

Spring Boot 3.3 / Java 21 backend for gradual routing away from the current FastAPI service. The supported migration surface is `/api/v2`: it validates the JWT issued by FastAPI and provides read-only master-data and reporting endpoints. FastAPI `/api/v1` remains the only production writer.

The repository already contained experimental Java `/api/v1` code before this read-only slice was added. Nginx must expose only Java `/api/v2`; do not route Java `/api/v1` in production. The Java datasource is configured read-only at both Hikari and PostgreSQL session level, so legacy Java write methods are not operational under this configuration.

## Requirements and start

- Java 21
- Maven 3.9+
- The existing PostgreSQL database

From `backend-java/`:

```powershell
$env:YUKI_DB_URL = 'jdbc:postgresql://localhost:5432/dlx_yuki_wms'
$env:YUKI_DB_USER = 'dlx_user'
$env:YUKI_DB_PASSWORD = '<your-read-only-database-password>'
$env:YUKI_JWT_SECRET = '<same-secret-as-fastapi>'
mvn spring-boot:run
```

The default Java port is `8081`. `YUKI_SERVER_PORT` overrides it. Compatibility fallbacks `DATABASE_URL`, `JWT_SECRET_KEY`, and `PORT` are retained; the Java-specific variables take precedence. Credentials can alternatively be supplied as `YUKI_DB_USER` and `YUKI_DB_PASSWORD`.

Useful checks:

```powershell
Invoke-RestMethod http://localhost:8081/api/v2/health
Invoke-RestMethod http://localhost:8081/api/v2/health/db
mvn -q test
mvn -q -DskipTests package
```

OpenAPI JSON is at `/api/v2/openapi`; Swagger UI is at `/api/v2/swagger-ui.html`.

## Supported `/api/v2` surface

- `GET /api/v2/health`
- `GET /api/v2/health/db`
- `GET /api/v2/customers`
- `GET /api/v2/warehouses`
- `GET /api/v2/carriers`
- `GET /api/v2/fc-addresses`
- `GET /api/v2/reporting/dashboard`

Except for health and API documentation, endpoints require `Authorization: Bearer <FastAPI access token>`. Missing and invalid credentials keep the production JSON error envelope (`detail`). Customer and warehouse restrictions use the existing user scope records.

## Non-negotiable database boundary

Flyway is disabled. This service contains no migration and must never create, alter, or drop a table. PostgreSQL connections execute `SET default_transaction_read_only = on`, and the MyBatis v2 mapper contains only explicit `SELECT` statements.

Use a dedicated PostgreSQL read-only account in deployed environments. Application-level read-only annotations are defense in depth, not a substitute for database grants.

## Migration and routing order

1. Apply schema changes, if any, through the existing Python/Alembic release process only.
2. Deploy FastAPI and verify `/api/v1` writes first.
3. Deploy Java on port 8081 with read-only database credentials.
4. Verify `/api/v2/health/db`, authentication, scope filtering, and report parity.
5. Add the Nginx split using `nginx/yuki-wms-split.conf.example`.
6. Migrate in this order: reporting first, then Inbound/Inventory queries, and only after an explicit ownership handoff consider Outbound writes.

Until that future ownership handoff is separately designed, reviewed, and deployed, leave every write on FastAPI `/api/v1`. The Java service delivered here has no supported write route.

Maintain the **single-writer rule** throughout migration: FastAPI `/api/v1` owns all writes, transactions, login, refresh, and schema migrations. Java `/api/v2` owns only reads and reports.

The repository findings used to establish this boundary are recorded in `docs/discovery.md`.
