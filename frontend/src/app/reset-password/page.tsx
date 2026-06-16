"use client";

import * as React from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";

const schema = z
  .object({
    new_password: z
      .string()
      .min(12, "At least 12 characters")
      .max(128, "Too long")
      .regex(/[A-Z]/, "Include at least one uppercase letter")
      .regex(/[a-z]/, "Include at least one lowercase letter")
      .regex(/\d/, "Include at least one digit"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });

type Values = z.infer<typeof schema>;

export default function ResetPasswordPage(): React.ReactElement {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");
  const [done, setDone] = React.useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Values): Promise<void> {
    if (!token) {
      toast.error("Missing reset token. Open the link from your email again.");
      return;
    }
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: values.new_password,
      });
      setDone(true);
      toast.success("Password reset. Please sign in with your new password.");
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : "Could not reset password. The link may have expired.",
      );
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/30 px-4 py-12">
      <main id="main" className="w-full max-w-md">
        <Card>
          <CardHeader>
            <CardTitle>Set a new password</CardTitle>
            <CardDescription>
              Pick a strong password — minimum 12 characters with upper, lower, and a digit.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {done ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-md border border-profit/30 bg-profit/5 p-3 text-sm text-profit">
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  Password updated. Redirecting to sign-in…
                </div>
                <Button asChild className="w-full" variant="brand">
                  <Link href="/login">Sign in now</Link>
                </Button>
              </div>
            ) : !token ? (
              <div className="space-y-3 text-sm">
                <p>The link is missing the reset token. Please open the latest link from your email.</p>
                <Button asChild variant="outline" className="w-full">
                  <Link href="/forgot-password">Request a new link</Link>
                </Button>
              </div>
            ) : (
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
                <div className="space-y-1.5">
                  <Label htmlFor="new-pw">New password</Label>
                  <Input
                    id="new-pw"
                    type="password"
                    autoComplete="new-password"
                    {...register("new_password")}
                    aria-invalid={!!errors.new_password}
                  />
                  {errors.new_password && (
                    <p role="alert" className="text-xs text-destructive">
                      {errors.new_password.message}
                    </p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="confirm-pw">Confirm password</Label>
                  <Input
                    id="confirm-pw"
                    type="password"
                    autoComplete="new-password"
                    {...register("confirm")}
                    aria-invalid={!!errors.confirm}
                  />
                  {errors.confirm && (
                    <p role="alert" className="text-xs text-destructive">
                      {errors.confirm.message}
                    </p>
                  )}
                </div>
                <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? "Saving…" : "Reset password"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
