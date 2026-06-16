# syntax=docker/dockerfile:1.7
# ============================================================================
# infra/docker/frontend.Dockerfile — Next.js standalone runtime image
# ============================================================================
# Multi-stage build:
#   1. deps     — install pnpm deps (cached layer)
#   2. builder  — `next build` produces .next/standalone
#   3. runtime  — minimal image with node + standalone bundle
# Build context: ./frontend  (override `dockerfile:` path in compose).
# ============================================================================

# ===== Stage 1: dependencies =====
FROM node:20.18-alpine AS deps
RUN apk add --no-cache libc6-compat \
    && corepack enable \
    && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
# If pnpm-lock.yaml exists, prefer frozen install. Otherwise fall back so first
# commit doesn't break the image build.
RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm install --frozen-lockfile; \
    else \
        pnpm install --no-frozen-lockfile; \
    fi

# ===== Stage 2: builder =====
FROM node:20.18-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate production build (Next.js writes .next/standalone because of
# `output: "standalone"` in next.config.ts).
RUN pnpm build

# ===== Stage 3: runtime =====
FROM node:20.18-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Standalone server + static assets + public dir.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

# /api/health is a simple route that returns 200 if the server is up.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000/api/health || exit 1

CMD ["node", "server.js"]
