/**
 * NextAuth wiring against the Forex Bot API.
 * Reference: docs/api/openapi.yaml — /auth/login, /auth/refresh, /users/me.
 *
 * Access tokens live 15 min by default; refresh tokens are long-lived.
 * Strategy:
 *   1. Credentials authorize() calls POST /auth/login → store both tokens + expiry in JWT.
 *   2. jwt() callback refreshes via POST /auth/refresh when access expires
 *      (< 60s remaining). On failure, session is flagged with `error` and the
 *      client should sign out.
 *   3. session() exposes accessToken to the browser for use by `api.*` calls.
 *
 * Vercel notes:
 *   - NEXTAUTH_URL: optional in Next 15 — falls back to VERCEL_URL on previews.
 *     We set `trustHost: true` so NextAuth trusts the x-forwarded-host header
 *     from the Vercel edge proxy.
 *   - Cookies are scoped `__Secure-` in production over HTTPS. NextAuth defaults
 *     already do this when running on HTTPS; we keep it explicit so cold-starts
 *     and previews behave identically.
 *   - JWT secret must be set via NEXTAUTH_SECRET. We do NOT fall back to a
 *     default in production — a missing secret throws at first request.
 */

import type { NextAuthOptions } from "next-auth";
import type { JWT } from "next-auth/jwt";
import CredentialsProvider from "next-auth/providers/credentials";
import { ApiError, api } from "@/lib/api";
import type { TokenPair, UserPublic } from "@/types";

/** Convert a 15-min access token + lifetime into an absolute epoch (seconds). */
function expiresAtFromLifetime(expiresIn: number): number {
  return Math.floor(Date.now() / 1000) + Math.max(expiresIn - 5, 30);
}

async function fetchProfile(accessToken: string): Promise<UserPublic> {
  return api.get<UserPublic>("/users/me", { token: accessToken });
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const fresh = await api.post<TokenPair>("/auth/refresh", {
      refresh_token: token.refreshToken,
    });
    return {
      ...token,
      accessToken: fresh.access_token,
      refreshToken: fresh.refresh_token,
      accessTokenExpiresAt: expiresAtFromLifetime(fresh.expires_in),
      error: undefined,
    };
  } catch {
    return { ...token, error: "RefreshAccessTokenError" };
  }
}

const isProduction = process.env.NODE_ENV === "production";

/**
 * On Vercel, NEXTAUTH_URL is optional — VERCEL_URL is auto-injected per deploy.
 * Setting `trustHost: true` lets NextAuth honour the proxied x-forwarded-host.
 */
const cookiePrefix = isProduction ? "__Secure-" : "";

export const authOptions: NextAuthOptions = {
  // SECURITY: secret must be provided — we deliberately do NOT default it.
  secret: process.env.NEXTAUTH_SECRET,
  // Vercel + custom domains both terminate TLS at the edge. Trust the proxy.
  useSecureCookies: isProduction,
  providers: [
    CredentialsProvider({
      id: "credentials",
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
        totp: { label: "2FA code", type: "text" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials.password) return null;
        try {
          const tokens = await api.post<TokenPair>("/auth/login", {
            email: credentials.email,
            password: credentials.password,
            totp_code: credentials.totp || null,
          });
          const profile = await fetchProfile(tokens.access_token);
          return {
            id: profile.id,
            email: profile.email,
            name: profile.display_name ?? profile.email,
            isAdmin: profile.is_admin,
            emailVerified: profile.is_email_verified,
            totpEnabled: profile.totp_enabled,
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            accessTokenExpiresAt: expiresAtFromLifetime(tokens.expires_in),
          };
        } catch (err) {
          if (err instanceof ApiError) {
            // Map common cases to clear messages — NextAuth surfaces these in `result.error`.
            if (err.status === 401) throw new Error("Invalid email or password");
            if (err.status === 429) throw new Error("Too many attempts. Try again shortly.");
            throw new Error(err.message);
          }
          return null;
        }
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24 * 30, // 30 days; access token still rotates every ~15 min.
  },
  jwt: {
    // NextAuth uses NEXTAUTH_SECRET by default; explicit maxAge keeps JWT and
    // session lifetimes aligned so a stale token can't outlive its session row.
    maxAge: 60 * 60 * 24 * 30,
  },
  cookies: {
    sessionToken: {
      name: `${cookiePrefix}next-auth.session-token`,
      options: {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        secure: isProduction,
      },
    },
    callbackUrl: {
      name: `${cookiePrefix}next-auth.callback-url`,
      options: {
        sameSite: "lax",
        path: "/",
        secure: isProduction,
      },
    },
    csrfToken: {
      // CSRF cookie is double-submit; Host prefix in prod.
      name: `${isProduction ? "__Host-" : ""}next-auth.csrf-token`,
      options: {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        secure: isProduction,
      },
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      // First sign-in: seed JWT from User. We cast because the User | AdapterUser
      // union widens our augmented `emailVerified: boolean` back to `Date | null`.
      if (user) {
        const u = user as unknown as import("next-auth").User;
        return {
          ...token,
          id: u.id,
          email: u.email,
          name: u.name,
          isAdmin: u.isAdmin,
          emailVerified: u.emailVerified,
          totpEnabled: u.totpEnabled,
          accessToken: u.accessToken,
          refreshToken: u.refreshToken,
          accessTokenExpiresAt: u.accessTokenExpiresAt,
        } as typeof token;
      }

      if (!token.accessToken || !token.refreshToken) {
        return { ...token, error: "MissingTokens" };
      }

      const now = Math.floor(Date.now() / 1000);
      const expiringSoon = token.accessTokenExpiresAt - now < 60;
      if (!expiringSoon) {
        return token;
      }
      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.error = token.error;
      session.user = {
        id: token.id,
        email: token.email,
        name: token.name,
        isAdmin: token.isAdmin,
        emailVerified: token.emailVerified,
        totpEnabled: token.totpEnabled,
      };
      return session;
    },
  },
  // NEXTAUTH_DEBUG in env enables verbose logs on previews. Off in prod.
  debug: !isProduction && process.env.NEXTAUTH_DEBUG === "true",
};
