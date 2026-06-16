import { NextResponse } from "next/server";
import { withAuth } from "next-auth/middleware";

/**
 * Next-Auth middleware.
 *
 * Two concerns layered on the same edge function:
 *   1. Anyone hitting an authenticated route must have a valid session.
 *   2. /admin/* additionally requires `isAdmin === true` on the JWT.
 *
 * Defence in depth — even if the token claim were forged, the backend revalidates
 * the role server-side via the Bearer token. This guard exists for UX and to
 * keep static/JS bundles out of non-admin browser caches.
 */
export default withAuth(
  function onAuthorized(req) {
    const { pathname } = req.nextUrl;
    const token = req.nextauth?.token;
    if (pathname.startsWith("/admin")) {
      if (!token?.isAdmin) {
        const url = req.nextUrl.clone();
        url.pathname = "/dashboard";
        url.searchParams.set("admin_denied", "1");
        return NextResponse.redirect(url);
      }
    }
    return NextResponse.next();
  },
  {
    pages: { signIn: "/login" },
    callbacks: {
      authorized: ({ token, req }) => {
        if (!token) return false;
        if (req.nextUrl.pathname.startsWith("/admin")) {
          return Boolean(token.isAdmin);
        }
        return true;
      },
    },
  },
);

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/strategies/:path*",
    "/backtest/:path*",
    "/broker/:path*",
    "/billing/:path*",
    "/settings/:path*",
    "/onboarding/:path*",
    "/admin/:path*",
  ],
};
