"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  Bell,
  Download,
  ExternalLink,
  FileLock2,
  KeyRound,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserRound,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useMe } from "@/hooks/use-me";
import { useTotpEnroll, useTotpVerify } from "@/hooks/use-totp";
import { useDeleteAccount, useExportMyData } from "@/hooks/use-account";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import { TotpQrCode } from "@/components/totp-qr-code";

const DELETE_PHRASE = "DELETE MY ACCOUNT";

// Placeholder consent log until /users/me/consents lands.
const CONSENT_LOG: ReadonlyArray<{
  type: string;
  version: string;
  acknowledged_at: string;
}> = [];

export default function SettingsPage() {
  const me = useMe();
  const enroll = useTotpEnroll();
  const verify = useTotpVerify();
  const exportData = useExportMyData();
  const deleteAccount = useDeleteAccount();
  const [provisioningUri, setProvisioningUri] = React.useState<string | null>(null);
  const [secret, setSecret] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [deletePhrase, setDeletePhrase] = React.useState("");

  async function handleExport(): Promise<void> {
    try {
      const res = await exportData.mutateAsync();
      toast.success(res.message ?? "We'll email you a download link.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        toast.success("Export queued — we'll email you the link.");
        return;
      }
      toast.error(err instanceof ApiError ? err.message : "Could not start export");
    }
  }

  async function handleDelete(): Promise<void> {
    if (deletePhrase.trim() !== DELETE_PHRASE) {
      toast.error(`Type the exact phrase: ${DELETE_PHRASE}`);
      return;
    }
    try {
      await deleteAccount.mutateAsync({ confirmation_phrase: deletePhrase.trim() });
      toast.success("Account scheduled for deletion. 30-day grace period started.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete account");
    }
  }

  async function handleEnroll() {
    try {
      const res = await enroll.mutateAsync();
      setProvisioningUri(res.provisioning_uri);
      setSecret(res.secret);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start 2FA enrollment");
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      toast.error("Enter the 6-digit code from your authenticator");
      return;
    }
    try {
      await verify.mutateAsync(code);
      toast.success("Two-factor authentication enabled");
      setProvisioningUri(null);
      setSecret(null);
      setCode("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Invalid code, try again");
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your account, security, and alerts.</p>
      </header>

      <Tabs defaultValue="account">
        <TabsList>
          <TabsTrigger value="account">
            <UserRound className="mr-2 h-4 w-4" aria-hidden="true" />
            Account
          </TabsTrigger>
          <TabsTrigger value="security">
            <ShieldCheck className="mr-2 h-4 w-4" aria-hidden="true" />
            Security
          </TabsTrigger>
          <TabsTrigger value="notifications">
            <Bell className="mr-2 h-4 w-4" aria-hidden="true" />
            Notifications
          </TabsTrigger>
          <TabsTrigger value="privacy">
            <FileLock2 className="mr-2 h-4 w-4" aria-hidden="true" />
            Privacy
          </TabsTrigger>
          {me.data?.is_admin && (
            <TabsTrigger value="admin">
              <ShieldAlert className="mr-2 h-4 w-4 text-destructive" aria-hidden="true" />
              Admin tools
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="account">
          <Card>
            <CardHeader>
              <CardTitle>Account</CardTitle>
              <CardDescription>Profile and contact information.</CardDescription>
            </CardHeader>
            <CardContent>
              {me.isLoading || !me.data ? (
                <Skeleton className="h-32" />
              ) : (
                <form className="space-y-4 sm:max-w-md">
                  <div className="space-y-1.5">
                    <Label htmlFor="full-name">Display name</Label>
                    <Input
                      id="full-name"
                      defaultValue={me.data.display_name ?? ""}
                      readOnly
                      aria-describedby="name-help"
                    />
                    <p id="name-help" className="text-xs text-muted-foreground">
                      Editing your display name is coming soon.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="email-readonly">Email</Label>
                    <Input id="email-readonly" defaultValue={me.data.email} readOnly />
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="h-5 w-5" aria-hidden="true" />
                Change password
              </CardTitle>
              <CardDescription>
                Password change is performed via email recovery. Send yourself a reset link from
                the sign-in page.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <a href="/forgot-password">Send password reset link</a>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" aria-hidden="true" />
                Two-factor authentication
              </CardTitle>
              <CardDescription>
                Protect your account with a TOTP authenticator like 1Password, Authy or Google
                Authenticator.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {me.isLoading || !me.data ? (
                <Skeleton className="h-12" />
              ) : (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">Authenticator app</p>
                      <p className="text-xs text-muted-foreground">
                        Currently {me.data.totp_enabled ? "enabled" : "disabled"}
                      </p>
                    </div>
                    {!me.data.totp_enabled && !provisioningUri && (
                      <Button variant="outline" onClick={handleEnroll} disabled={enroll.isPending}>
                        {enroll.isPending ? "Starting…" : "Set up"}
                      </Button>
                    )}
                  </div>
                  {provisioningUri && (
                    <div className="space-y-4 rounded-md border p-4">
                      <p className="text-sm">
                        Scan this QR code with your authenticator app, then enter the 6-digit code
                        below.
                      </p>
                      <TotpQrCode uri={provisioningUri} />
                      {secret && (
                        <p className="break-all rounded-md bg-muted px-3 py-2 text-xs font-mono">
                          Secret: {secret}
                        </p>
                      )}
                      <form onSubmit={handleVerify} className="flex flex-wrap items-end gap-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="totp-verify">6-digit code</Label>
                          <Input
                            id="totp-verify"
                            inputMode="numeric"
                            maxLength={6}
                            value={code}
                            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                            className="w-32"
                          />
                        </div>
                        <Button type="submit" variant="brand" disabled={verify.isPending}>
                          {verify.isPending ? "Verifying…" : "Verify & enable"}
                        </Button>
                      </form>
                    </div>
                  )}
                </>
              )}
              <Separator />
              <p className="text-xs text-muted-foreground">
                When 2FA is on you&apos;ll be asked for a 6-digit code at sign-in.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle>Notifications</CardTitle>
              <CardDescription>
                Choose how we reach you when strategies act or alerts fire.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {[
                {
                  id: "n-signals",
                  title: "Strategy signals",
                  desc: "Email me when a strategy opens or closes a trade.",
                  defaultChecked: true,
                },
                {
                  id: "n-drawdown",
                  title: "Drawdown alerts",
                  desc: "Notify me if my account drawdown exceeds 5% in one day.",
                  defaultChecked: true,
                },
                {
                  id: "n-marketing",
                  title: "Product updates",
                  desc: "Occasional updates about new strategies and features.",
                  defaultChecked: false,
                },
              ].map((row) => (
                <div key={row.id} className="flex items-start justify-between gap-3">
                  <div>
                    <Label htmlFor={row.id} className="text-sm font-medium">
                      {row.title}
                    </Label>
                    <p className="mt-1 text-xs text-muted-foreground">{row.desc}</p>
                  </div>
                  <Switch id={row.id} defaultChecked={row.defaultChecked} />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="privacy" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Download className="h-5 w-5" aria-hidden="true" />
                {t("settings.gdpr.title")}
              </CardTitle>
              <CardDescription>{t("settings.gdpr.export.note")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button variant="outline" onClick={handleExport} disabled={exportData.isPending}>
                {exportData.isPending ? "Queuing…" : t("settings.gdpr.export")}
              </Button>
              <Separator />
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-destructive">
                  {t("settings.gdpr.delete")}
                </h3>
                <p className="text-xs text-muted-foreground">{t("settings.gdpr.delete.note")}</p>
                <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
                  <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
                  {t("settings.gdpr.delete")}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("settings.consent.title")}</CardTitle>
              <CardDescription>
                Versioned record of every consent you have given.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {CONSENT_LOG.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Consent log is empty. Items you accept (risk disclosure, live trading) appear here.
                </p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {CONSENT_LOG.map((c) => (
                    <li
                      key={`${c.type}-${c.version}-${c.acknowledged_at}`}
                      className="flex items-start justify-between gap-3 rounded-md border p-3"
                    >
                      <div>
                        <p className="font-medium">{c.type}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(c.acknowledged_at).toLocaleString()}
                        </p>
                      </div>
                      <Badge variant="outline">v{c.version}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {me.data?.is_admin && (
          <TabsContent value="admin">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldAlert className="h-5 w-5 text-destructive" aria-hidden="true" />
                  Admin tools
                </CardTitle>
                <CardDescription>
                  You have elevated permissions. Actions in the admin panel are logged and audited.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="destructive">
                  <Link href="/admin">
                    <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
                    Open Admin Panel
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              We will pause your strategies immediately and purge your personal data after a 30-day
              grace period. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="delete-phrase">
              Type <code className="rounded bg-muted px-1 py-0.5 text-xs">{DELETE_PHRASE}</code> to
              confirm
            </Label>
            <Input
              id="delete-phrase"
              value={deletePhrase}
              onChange={(e) => setDeletePhrase(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deletePhrase.trim() !== DELETE_PHRASE || deleteAccount.isPending}
            >
              {deleteAccount.isPending ? "Scheduling…" : "Delete my account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
