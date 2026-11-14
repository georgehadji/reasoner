# Deploying on Oracle Cloud Always Free

Runs the whole `docker-compose.yml` stack (Caddy, backend, frontend, Postgres,
Valkey) on one Always Free Arm VM, with `docker-compose.oracle.yml` on top.
This is a delta on `DEPLOY.md`: read that for the full `.env` reference,
data-directory ownership and day-two commands.

Nothing here has been run on a real Oracle VM. What was checked locally:
`docker compose config` merges the two files as intended, and `caddy adapt`
accepts `Caddyfile.prod`. Hosting is free; LLM calls are not: every run still
bills OpenRouter or whichever provider keys you set.

## What Always Free gives you

From Oracle's Always Free page (checked 2026-11-11):

- `VM.Standard.A1.Flex` (Arm): 1,500 OCPU-hours and 9,000 GB-hours a month,
  which is 2 OCPUs and 12 GB, as one VM or two.
- 200 GB of block storage in the home region, boot and block volumes combined,
  plus five volume backups.
- An Always Free instance is reclaimed as idle when, over 7 days, its 95th
  percentile CPU, its network and (A1 only) its memory utilisation are **all**
  under 20%. See "Idle reclaim" below.

## 1. Create the VM

1. Create an instance in your **home region** (other regions are billed).
2. Image: Canonical Ubuntu 24.04, aarch64. Shape: `VM.Standard.A1.Flex`,
   2 OCPU, 12 GB.
3. Boot volume: 100 GB (Postgres, uploads and Docker images all live on it).
4. Assign a public IPv4 address and add your SSH public key.

"Out of capacity" is common for A1. Retry later or pick another availability
domain.

## 2. Open ports 80 and 443

1. In the VCN's security list (or the instance's NSG), add ingress rules for
   TCP 80 and 443 from `0.0.0.0/0`. Restrict TCP 22 to your own IP.
2. Oracle's Ubuntu images ship host firewall rules that reject inbound traffic
   other than SSH. Allow 80 and 443 there too and persist the rules:

   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

## 3. Point a domain at the VM

Create an `A` record for your domain to the VM's public IP. Caddy needs it to
resolve before it can get a Let's Encrypt certificate. With no domain of your
own, a free dynamic-DNS subdomain (DuckDNS, for example) works.

## 4. Install Docker and get the code

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # log out and back in
git clone <your repo URL> reasoner && cd reasoner
```

## 5. Configure `.env`

```bash
cp .env.example .env
```

Set at least these (generate secrets with `openssl rand -hex 32`):

| Variable | Value |
|----------|-------|
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.oracle.yml` |
| `DOMAIN` | your domain, e.g. `reasoner.example.org` |
| `ACME_EMAIL` | email for Let's Encrypt notices |
| `CORS_ORIGINS` | `https://<DOMAIN>` |
| `POSTGRES_PASSWORD` | random |
| `ADMIN_API_KEY`, `CSRF_SECRET` | random, at least 32 characters (startup refuses less in production) |
| `JWT_SECRET_KEY` | random, at least 32 characters |
| `OPENROUTER_API_KEY` | your key |

`COMPOSE_FILE` makes every plain `docker compose ...` command, including the
ones in `DEPLOY.md`, use both files. `ENVIRONMENT=production`, `DATABASE_URL`
and `VALKEY_URL` are set by the compose file and override `.env`. Supabase,
billing, search and Sentry variables are in `DEPLOY.md` Step 1.

`TRUSTED_PROXIES` is set by the override (Caddy and the Next.js server have
pinned addresses on `172.28.0.0/24`); leave it out of `.env`.

## 6. Data directories, then start

Create and hand over the bind-mounted directories as in `DEPLOY.md` Step 2b,
then build and start. The first build on 2 OCPUs takes a while.

```bash
docker compose up -d --build
docker compose ps
curl -fsS "https://$DOMAIN/api/health"
```

## What the override changes

| Service | Change |
|---------|--------|
| caddy | Mounts `Caddyfile.prod` (HTTPS, security headers) instead of the dev `:80` file; gets `DOMAIN`, `ACME_EMAIL` |
| backend | 3 workers instead of 8 (`UVICORN_WORKERS` in `.env` overrides); limit 1.5 CPU, 3 GB |
| caddy, frontend | Fixed addresses `172.28.0.10` and `.11`, named in `TRUSTED_PROXIES` |
| docker-socket-proxy, sandbox-worker | Behind the `sandbox` profile, so they do not start. Code execution stays off, as `EXEC_SANDBOX_ENABLED` defaults to false |

## Idle reclaim

Oracle reclaims an Always Free instance only when CPU, network and memory are
all under 20% for 7 days. Memory is the easiest to keep above the line: 20% of
12 GB is about 2.4 GB. After a day of normal use, check with `free -m` and
`docker stats`. If a quiet instance sits below that, the options are real
traffic or upgrading the account to Pay As You Go. Oracle states Always Free
resources stay free after the upgrade; its page does not say whether upgraded
accounts are exempt from idle reclaim. Set a budget alert if you upgrade.

## Backups

- Database: `pg_dump` as in `DEPLOY.md` ("Backup database"), copied off the VM.
- Volumes: a boot-volume backup policy within the five free backups.

## Updating

```bash
git pull
docker compose up -d --build
```

## Not verified

- Building `Dockerfile` (Python 3.14, `requirements.txt`) and `ui-next/Dockerfile`
  on arm64. Any dependency without an aarch64 wheel compiles from source in the
  builder stage (it has `gcc`) or fails there.
- arm64 images for `tecnativa/docker-socket-proxy` and the sandbox image.
- Whether Oracle's host firewall blocks Docker-published ports without the
  `iptables` step in section 2.
- Memory use of the running stack against the idle-reclaim line.
