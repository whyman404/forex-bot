"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";

type Status = "idle" | "verifying" | "success" | "error";

export default function VerifyEmailPage(): React.ReactElement {
  const params = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = React.useState<Status>("idle");
  const [errorMessage, setErrorMessage] = React.useState<string>("");

  React.useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMessage("Missing verification token. Please use the link from your email.");
      return;
    }
    let cancelled = false;
    void (async () => {
      setStatus("verifying");
      try {
        await api.post("/auth/verify-email", { token });
        if (!cancelled) setStatus("success");
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          err instanceof ApiError
            ? err.message
            : "Could not verify your email. The link may have expired.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/30 px-4 py-12">
      <main id="main" className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              {status === "verifying" || status === "idle" ? (
                <Loader2 className="h-6 w-6 animate-spin text-brand" aria-hidden="true" />
              ) : status === "success" ? (
                <CheckCircle2 className="h-6 w-6 text-profit" aria-hidden="true" />
              ) : (
                <XCircle className="h-6 w-6 text-destructive" aria-hidden="true" />
              )}
            </div>
            <CardTitle>
              {status === "success"
                ? "Email verified"
                : status === "error"
                  ? "Verification failed"
                  : "Verifying your email…"}
            </CardTitle>
            <CardDescription>
              {status === "success"
                ? "Your email is confirmed. You can now sign in."
                : status === "error"
                  ? errorMessage
                  : "Hold tight, this only takes a moment."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {status === "success" && (
              <Button asChild className="w-full" variant="brand">
                <Link href="/login">Sign in</Link>
              </Button>
            )}
            {status === "error" && (
              <>
                <Button asChild className="w-full" variant="outline">
                  <Link href="/login">Back to sign in</Link>
                </Button>
                <p className="text-center text-xs text-muted-foreground">
                  Need a new link? Sign in and request a re-send from Settings.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
