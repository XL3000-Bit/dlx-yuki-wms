# DLX Yuki WMS - Oracle Cloud Deployment

This deployment targets an Oracle Cloud Ubuntu ARM64 VM (VM.Standard.A1.Flex) using Docker Compose.

## 1. Oracle VM

Recommended Always Free shape:
- Image: Ubuntu 24.04 (aarch64)
- Shape: VM.Standard.A1.Flex
- OCPU: 2
- Memory: 12 GB
- Public IPv4: enabled
- Boot volume: 50 GB or more while staying inside the Always Free storage allowance

Open inbound TCP ports 22, 80, and later 443 in the OCI subnet Security List or NSG.

## 2. Connect to the VM

```bash
ssh -i /path/to/private.key ubuntu@YOUR_PUBLIC_IP
```

## 3. Install Docker and Git

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

docker --version
docker compose version
```

## 4. Clone the deployment branch

```bash
git clone -b deploy/oracle-cloud https://github.com/XL3000-Bit/dlx-yuki-wms.git
cd dlx-yuki-wms
```

For a private repository, authenticate with GitHub using an approved credential method rather than putting a token in shell history.

## 5. Configure secrets

```bash
cp deploy/oracle/.env.example deploy/oracle/.env
chmod 600 deploy/oracle/.env
nano deploy/oracle/.env
```

Set at minimum:
- POSTGRES_PASSWORD to a long random password
- JWT_SECRET_KEY to a random value of at least 32 characters
- CORS_ORIGINS to ["http://YOUR_PUBLIC_IP"] for initial HTTP testing

Generate secrets without storing them in Git:

```bash
openssl rand -hex 32
openssl rand -base64 48
```

## 6. Start PostgreSQL first

```bash
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml up -d postgres
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml ps
```

## 7. Build backend and run migrations

```bash
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml build backend
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml run --rm backend alembic upgrade head
```

Do not continue if the migration command fails.

## 8. Start the full stack

```bash
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml up -d --build
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml ps
```

## 9. Verify from the VM

```bash
curl -f http://127.0.0.1/health
curl -I http://127.0.0.1/
```

Then open http://YOUR_PUBLIC_IP in a browser.

The backend is not exposed publicly. Nginx serves React and proxies /api/* to FastAPI on the private Docker network.

## 10. Create the first administrator

Create the first administrator exactly once using the existing bootstrap endpoint after migrations and health checks pass. Do not expose or commit administrator credentials.

## 11. Logs and status

```bash
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml ps
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml logs --tail=200 backend
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml logs --tail=200 frontend
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml logs --tail=200 postgres
```

## 12. Update deployment

```bash
cd ~/dlx-yuki-wms
git pull
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml build
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml run --rm backend alembic upgrade head
docker compose --env-file deploy/oracle/.env -f docker-compose.oracle.yml up -d
```

## 13. Persistence

PostgreSQL, uploaded documents, and backup data live in named Docker volumes. docker compose down does not delete them. Do not run docker compose down -v on a production server unless permanent data deletion is intended.

## 14. HTTPS

Initial smoke testing can use the public IP over HTTP. Before daily warehouse use, point a domain or subdomain to the Oracle public IP, open TCP 443, add TLS/HTTPS, and update CORS_ORIGINS to the final HTTPS origin.
