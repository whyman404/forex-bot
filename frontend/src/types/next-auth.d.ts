import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface User {
    id: string;
    email: string;
    name: string;
    isAdmin: boolean;
    emailVerified: boolean;
    totpEnabled: boolean;
    accessToken: string;
    refreshToken: string;
    /** Seconds since epoch when access token expires. */
    accessTokenExpiresAt: number;
  }
  interface Session {
    accessToken?: string;
    error?: "RefreshAccessTokenError" | "MissingTokens";
    user: {
      id: string;
      email: string;
      name: string;
      isAdmin: boolean;
      emailVerified: boolean;
      totpEnabled: boolean;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    email: string;
    name: string;
    isAdmin: boolean;
    emailVerified: boolean;
    totpEnabled: boolean;
    accessToken: string;
    refreshToken: string;
    accessTokenExpiresAt: number;
    error?: "RefreshAccessTokenError" | "MissingTokens";
  }
}
