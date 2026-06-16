"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";

/**
 * Centralised access-token getter that triggers sign-out when the underlying
 * refresh flow has failed. Returns null while the session is loading or
 * unauthenticated so query hooks can stay `enabled`-gated.
 */
export function useSessionToken(): {
  token: string | null;
  status: "loading" | "authenticated" | "unauthenticated";
} {
  const { data: session, status } = useSession();

  React.useEffect(() => {
    if (session?.error === "RefreshAccessTokenError" || session?.error === "MissingTokens") {
      signOut({ callbackUrl: "/login" });
    }
  }, [session?.error]);

  if (status !== "authenticated" || !session?.accessToken) {
    return { token: null, status };
  }
  return { token: session.accessToken, status };
}
