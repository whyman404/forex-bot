import { withAuth } from "next-auth/middleware";

/**
 * Next-Auth middleware — bounce unauthenticated users to /login.
 * Matcher covers everything in the (app) route group.
 */
export default withAuth({
  pages: { signIn: "/login" },
});

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/strategies/:path*",
    "/backtest/:path*",
    "/broker/:path*",
    "/billing/:path*",
    "/settings/:path*",
    "/onboarding/:path*",
  ],
};
