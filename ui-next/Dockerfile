# ── Frontend Dockerfile ──
FROM node:26-alpine AS builder

WORKDIR /app

COPY package*.json .
RUN npm ci

COPY . .
RUN npm run build

# ── Runtime stage ──
FROM node:26-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production

# Copy standalone output (~150MB vs 800MB with full node_modules)
# Critical Enhancement 5.7
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
COPY --chown=node:node https-server.js ./

# Run as the unprivileged `node` user (uid 1000) shipped in the base image.
# Trivy AVD-DS-0002: a container without a USER directive runs as root.
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider --no-check-certificate https://localhost:3000 || exit 1

CMD ["node", "https-server.js"]
