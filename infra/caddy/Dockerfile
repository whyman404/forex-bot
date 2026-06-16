# ============================================================================
# Caddy — production build with rate-limit + cloudflare-ip modules
# ============================================================================
# Built with xcaddy so we get caddy-ratelimit (mholt) and cloudflare-ip
# (WeidiDeng) which gives us proper IP allowlist enforcement.
#
# Build:
#   docker build -t forex-bot/caddy:2.8 infra/caddy/
# ============================================================================

FROM caddy:2.8-builder-alpine AS builder

RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit \
    --with github.com/WeidiDeng/caddy-cloudflare-ip

FROM caddy:2.8-alpine

# Copy custom binary
COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# Verify
RUN caddy version && caddy list-modules | grep -E "(ratelimit|cloudflare)"

# Logs directory (mounted from host)
RUN mkdir -p /var/log/caddy && chown -R caddy:caddy /var/log/caddy

# Caddy listens on 80/443 by default; admin API on 2019 (loopback only)
EXPOSE 80 443 443/udp 2019

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget --spider -q http://127.0.0.1:2019/config/ || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
