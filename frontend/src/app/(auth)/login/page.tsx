"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { env } from "@/lib/env";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "Password is at least 8 characters"),
  totp: z
    .string()
    .optional()
    .refine((v) => !v || /^\d{6}$/.test(v), "2FA code must be 6 digits"),
});

type LoginFormValues = z.infer<typeof schema>;

export default function LoginPage() {
  return (
    <React.Suspense fallback={null}>
      <LoginForm />
    </React.Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") ?? "/dashboard";
  const [formError, setFormError] = React.useState<string | null>(null);

  // Dev-mode prefill is ONLY shown when explicitly enabled AND not in Vercel
  // production. Vercel preview / production deployments default to false so
  // we never leak demo credentials in prod even if NEXT_PUBLIC_DEV_MODE is
  // accidentally checked in.
  const isProductionEnv =
    process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_VERCEL_ENV === "production";
  const devMode = env.NEXT_PUBLIC_DEV_MODE && !isProductionEnv;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(schema),
    defaultValues: devMode
      ? { email: "admin@local", password: "changeme123" }
      : { email: "", password: "" },
  });

  async function onSubmit(values: LoginFormValues) {
    setFormError(null);
    const res = await signIn("credentials", {
      email: values.email,
      password: values.password,
      totp: values.totp ?? "",
      redirect: false,
      callbackUrl,
    });
    if (!res || res.error) {
      const msg = res?.error ?? "Could not sign in";
      setFormError(msg);
      toast.error(msg);
      return;
    }
    toast.success("Welcome back");
    router.push(res.url ?? callbackUrl);
    router.refresh();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Welcome back. Enter your credentials to continue.
          {devMode && (
            <span className="mt-2 block rounded-md border border-dashed border-warn/40 bg-warn/5 px-2 py-1 text-xs">
              <strong>Dev mode:</strong> credentials prefilled with{" "}
              <code className="font-mono">admin@local / changeme123</code>.
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {formError && (
            <div
              role="alert"
              className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {formError}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "email-error" : undefined}
              {...register("email")}
            />
            {errors.email && (
              <p id="email-error" role="alert" className="text-xs text-destructive">
                {errors.email.message}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              <Link
                href="/forgot-password"
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Forgot password?
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "password-error" : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p id="password-error" role="alert" className="text-xs text-destructive">
                {errors.password.message}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="totp">2FA code (if enabled)</Label>
            <Input
              id="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="123456"
              {...register("totp")}
            />
            {errors.totp && (
              <p role="alert" className="text-xs text-destructive">
                {errors.totp.message}
              </p>
            )}
          </div>
          <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          New here?{" "}
          <Link href="/signup" className="font-medium text-foreground hover:underline">
            Create an account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
