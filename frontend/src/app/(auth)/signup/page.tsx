"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { env } from "@/lib/env";
import type { TokenPair } from "@/types";

const schema = z
  .object({
    name: z.string().min(2, "Name is at least 2 characters"),
    email: z.string().email("Enter a valid email"),
    password: z
      .string()
      .min(12, "Password is at least 12 characters")
      .regex(/[A-Z]/, "Include at least one uppercase letter")
      .regex(/[0-9]/, "Include at least one number"),
    confirm: z.string(),
    accept: z.literal(true, { errorMap: () => ({ message: "You must accept the terms" }) }),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });

type SignupValues = z.infer<typeof schema>;

export default function SignupPage() {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const devMode = env.NEXT_PUBLIC_DEV_MODE;

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: SignupValues) {
    setFormError(null);
    try {
      await api.post<TokenPair>("/auth/signup", {
        email: values.email,
        password: values.password,
        display_name: values.name,
      });

      if (devMode) {
        // Skip email verification in dev — sign in immediately.
        const res = await signIn("credentials", {
          email: values.email,
          password: values.password,
          totp: "",
          redirect: false,
          callbackUrl: "/dashboard",
        });
        if (res?.ok) {
          toast.success("Account created. Welcome aboard.");
          router.push("/dashboard");
          router.refresh();
          return;
        }
      }

      toast.success("Account created — please verify your email");
      router.push("/login");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not create account";
      setFormError(msg);
      toast.error(msg);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>Start with paper trading. No card required.</CardDescription>
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
            <Label htmlFor="name">Full name</Label>
            <Input id="name" autoComplete="name" {...register("name")} />
            {errors.name && (
              <p role="alert" className="text-xs text-destructive">
                {errors.name.message}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {errors.email && (
              <p role="alert" className="text-xs text-destructive">
                {errors.email.message}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register("password")}
              aria-describedby="password-help"
            />
            <p id="password-help" className="text-xs text-muted-foreground">
              At least 12 characters with one uppercase letter and one number.
            </p>
            {errors.password && (
              <p role="alert" className="text-xs text-destructive">
                {errors.password.message}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm">Confirm password</Label>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              {...register("confirm")}
            />
            {errors.confirm && (
              <p role="alert" className="text-xs text-destructive">
                {errors.confirm.message}
              </p>
            )}
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5" {...register("accept")} />
            <span>
              I agree to the{" "}
              <Link href="/legal/terms" className="underline">
                Terms
              </Link>{" "}
              and{" "}
              <Link href="/legal/privacy" className="underline">
                Privacy Policy
              </Link>
            </span>
          </label>
          {errors.accept && (
            <p role="alert" className="text-xs text-destructive">
              {errors.accept.message}
            </p>
          )}
          <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Creating…" : "Create account"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already a member?{" "}
          <Link href="/login" className="font-medium text-foreground hover:underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
