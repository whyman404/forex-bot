"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { format } from "date-fns";
import { AlertTriangle, Check, PlugZap, ShieldCheck, Trash2, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useBrokerAccounts,
  useCreateBrokerAccount,
  useDeleteBrokerAccount,
  useTestBrokerConnection,
} from "@/hooks/use-broker-accounts";
import { ApiError } from "@/lib/api";

const schema = z.object({
  label: z.string().min(2, "Label is too short"),
  account_type: z.enum(["demo", "live"]).default("demo"),
  server: z.string().min(2, "Server is required (e.g. ExnessKE-MT5Real8)"),
  login: z.string().regex(/^\d{4,}$/, "MT5 login is digits only"),
  password: z.string().min(6, "Password is too short"),
});

type Values = z.infer<typeof schema>;

export default function BrokerPage() {
  const accounts = useBrokerAccounts();
  const create = useCreateBrokerAccount();
  const remove = useDeleteBrokerAccount();
  const test = useTestBrokerConnection();
  const [testingId, setTestingId] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { account_type: "demo" },
  });

  async function onSubmit(values: Values) {
    try {
      await create.mutateAsync({
        broker: "exness_mt5",
        label: values.label,
        account_type: values.account_type,
        credentials: {
          server: values.server,
          login: values.login,
          password: values.password,
        },
      });
      toast.success(`Connected ${values.label}`);
      reset({ account_type: "demo" });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not connect broker");
    }
  }

  async function handleTest(id: string) {
    setTestingId(id);
    try {
      const result = await test.mutateAsync(id);
      toast[result.ok ? "success" : "error"](
        result.ok
          ? `Connection OK (${result.latency_ms ?? "?"} ms)`
          : (result.detail ?? "Connection failed"),
      );
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Test failed");
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Disconnect this broker account?")) return;
    try {
      await remove.mutateAsync(id);
      toast.success("Broker account removed");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete account");
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Broker connection</h1>
        <p className="text-sm text-muted-foreground">
          Connect your Exness MT5 account so the bot can place orders on your behalf.
        </p>
      </header>

      <Card className="border-destructive/40 bg-destructive/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            Before you connect
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            Use a <strong>dedicated MT5 trading password</strong>, not your Exness portal password.
            You can generate one from your Exness account area.
          </p>
          <p>
            Start with a <strong>demo or small live</strong> account. Verify the bot behaves as
            expected for at least one full session before scaling up.
          </p>
          <p className="flex items-start gap-2 text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            Credentials are encrypted at rest (AES-256-GCM) and never logged. Disconnect any time
            from this page.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PlugZap className="h-5 w-5" aria-hidden="true" />
            Connect MT5 account
          </CardTitle>
          <CardDescription>
            A dedicated MT5 terminal is provisioned per account on our Windows VPS.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="grid gap-4 sm:grid-cols-2"
            noValidate
            autoComplete="off"
          >
            <div className="space-y-1.5">
              <Label htmlFor="label">Label</Label>
              <Input id="label" placeholder="Main Exness" {...register("label")} />
              {errors.label && (
                <p role="alert" className="text-xs text-destructive">
                  {errors.label.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="account_type">Account type</Label>
              <select
                id="account_type"
                {...register("account_type")}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="demo">Demo</option>
                <option value="live">Live</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="server">MT5 server</Label>
              <Input id="server" placeholder="ExnessKE-MT5Real8" {...register("server")} />
              {errors.server && (
                <p role="alert" className="text-xs text-destructive">
                  {errors.server.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="login">MT5 login</Label>
              <Input id="login" inputMode="numeric" {...register("login")} />
              {errors.login && (
                <p role="alert" className="text-xs text-destructive">
                  {errors.login.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="password">Trading password</Label>
              <Input id="password" type="password" {...register("password")} />
              {errors.password && (
                <p role="alert" className="text-xs text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <Button type="submit" variant="brand" disabled={isSubmitting || create.isPending}>
                {create.isPending ? "Connecting…" : "Save & connect"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connected accounts</CardTitle>
          <CardDescription>
            Connected broker accounts. Use Test connection to verify credentials.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {accounts.isLoading ? (
            <Skeleton className="h-32" />
          ) : !accounts.data || accounts.data.length === 0 ? (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              No broker accounts connected yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead>Broker</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Last check</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {accounts.data.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-medium">{a.label}</TableCell>
                    <TableCell>{a.broker}</TableCell>
                    <TableCell>
                      <Badge variant={a.account_type === "live" ? "warn" : "secondary"}>
                        {a.account_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {a.last_connection_check_status === "ok" ? (
                        <span className="inline-flex items-center gap-1 text-xs text-profit">
                          <Check className="h-3 w-3" /> OK
                        </span>
                      ) : a.last_connection_check_status ? (
                        <span className="inline-flex items-center gap-1 text-xs text-destructive">
                          <X className="h-3 w-3" /> {a.last_connection_check_status}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">never</span>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {format(new Date(a.created_at), "MMM dd, yyyy")}
                    </TableCell>
                    <TableCell className="space-x-2 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleTest(a.id)}
                        disabled={testingId === a.id}
                      >
                        {testingId === a.id ? "Testing…" : "Test"}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDelete(a.id)}
                        aria-label={`Disconnect ${a.label}`}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
