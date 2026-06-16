"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  ClipboardList,
  CreditCard,
  KeyRound,
  PlugZap,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  useAdminUpdateUser,
  useAdminUser,
  useAdminUserBacktests,
  useAdminUserBrokerAccounts,
  useAdminUserConsents,
  useAdminUserInstances,
} from "@/hooks/admin/use-admin-users";
import { useAdminAuditLog } from "@/hooks/admin/use-admin-audit-log";
import { RoleBadge } from "@/components/admin/role-badge";
import { AuditLogEntry } from "@/components/admin/audit-log-entry";
import { ApiError } from "@/lib/api";
import type { UserRole } from "@/types/admin";

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const user = useAdminUser(id);
  const brokers = useAdminUserBrokerAccounts(id);
  const instances = useAdminUserInstances(id);
  const backtests = useAdminUserBacktests(id);
  const consents = useAdminUserConsents(id);
  const audit = useAdminAuditLog({ actor: id, per_page: 50 });
  const updateUser = useAdminUpdateUser();

  const [fullName, setFullName] = React.useState("");
  const [country, setCountry] = React.useState("");
  const [role, setRole] = React.useState<UserRole>("user");
  const [emailVerified, setEmailVerified] = React.useState(false);

  React.useEffect(() => {
    if (user.data) {
      setFullName(user.data.full_name ?? "");
      setCountry(user.data.country ?? "");
      setRole(user.data.role);
      setEmailVerified(user.data.is_email_verified);
    }
  }, [user.data]);

  async function handleSave() {
    if (!id) return;
    try {
      await updateUser.mutateAsync({
        id,
        body: {
          full_name: fullName,
          country,
          role,
          is_email_verified: emailVerified,
        },
      });
      toast.success("Profile updated.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Update failed");
    }
  }

  if (user.isLoading || !user.data) {
    return <Skeleton className="h-64" />;
  }
  if (user.error) {
    return (
      <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Failed to load user.
      </div>
    );
  }

  const u = user.data;

  return (
    <div className="space-y-4">
      <Button asChild variant="ghost" size="sm">
        <Link href="/admin/users">
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" /> Back to users
        </Link>
      </Button>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{u.full_name ?? u.email}</h1>
          <p className="text-sm text-muted-foreground">{u.email}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <RoleBadge role={u.role} />
            <Badge variant={u.status === "banned" ? "destructive" : "outline"}>{u.status}</Badge>
            {u.totp_enabled && (
              <Badge variant="secondary">
                <ShieldCheck className="mr-1 h-3 w-3" aria-hidden="true" /> 2FA
              </Badge>
            )}
            {u.subscription_plan && (
              <Badge variant="outline">
                {u.subscription_plan} · {u.subscription_status}
              </Badge>
            )}
          </div>
        </div>
      </header>

      <Tabs defaultValue="profile">
        <TabsList className="flex-wrap">
          <TabsTrigger value="profile">
            <UserRound className="mr-2 h-4 w-4" aria-hidden="true" /> Profile
          </TabsTrigger>
          <TabsTrigger value="subscriptions">
            <CreditCard className="mr-2 h-4 w-4" aria-hidden="true" /> Subscriptions
          </TabsTrigger>
          <TabsTrigger value="brokers">
            <PlugZap className="mr-2 h-4 w-4" aria-hidden="true" /> Brokers
          </TabsTrigger>
          <TabsTrigger value="instances">
            <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" /> Instances
          </TabsTrigger>
          <TabsTrigger value="backtests">
            <BookOpen className="mr-2 h-4 w-4" aria-hidden="true" /> Backtests
          </TabsTrigger>
          <TabsTrigger value="audit">
            <ClipboardList className="mr-2 h-4 w-4" aria-hidden="true" /> Audit
          </TabsTrigger>
          <TabsTrigger value="consents">
            <ShieldCheck className="mr-2 h-4 w-4" aria-hidden="true" /> Consents
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle>Profile</CardTitle>
              <CardDescription>Edits here are recorded in the audit log.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 sm:max-w-md">
              <div className="space-y-1.5">
                <Label htmlFor="ud-name">Full name</Label>
                <Input id="ud-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ud-country">Country</Label>
                <Input
                  id="ud-country"
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  maxLength={64}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ud-role">Role</Label>
                <select
                  id="ud-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                  className="h-10 w-full rounded-md border bg-background px-2 text-sm"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                  <option value="support">support</option>
                </select>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <Label htmlFor="ud-emailv">Email verified</Label>
                  <p className="text-xs text-muted-foreground">
                    Manually mark email as verified if confirmation was completed out-of-band.
                  </p>
                </div>
                <Switch
                  id="ud-emailv"
                  checked={emailVerified}
                  onCheckedChange={setEmailVerified}
                />
              </div>
              <Button onClick={handleSave} variant="brand" disabled={updateUser.isPending}>
                {updateUser.isPending ? "Saving…" : "Save changes"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="subscriptions">
          <Card>
            <CardHeader>
              <CardTitle>Subscriptions</CardTitle>
              <CardDescription>Current and historical billing — manual grants land here.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Current plan:{" "}
                <strong>
                  {u.subscription_plan ?? "free"} · {u.subscription_status ?? "inactive"}
                </strong>
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Manage from the{" "}
                <Link href="/admin/subscriptions" className="underline">
                  Subscriptions page
                </Link>{" "}
                to grant or cancel.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="brokers">
          <Card>
            <CardHeader>
              <CardTitle>Broker accounts</CardTitle>
              <CardDescription className="flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 text-warn" aria-hidden="true" />
                Metadata only — credentials are never shown to admins.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {brokers.isLoading ? (
                <Skeleton className="h-24" />
              ) : (brokers.data ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No broker accounts.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {brokers.data!.map((b) => (
                    <li key={b.id} className="flex items-center justify-between rounded-md border p-2">
                      <div>
                        <p className="font-medium">{b.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {b.broker} · {b.account_type}
                        </p>
                      </div>
                      <Badge variant={b.is_active ? "profit" : "outline"}>
                        {b.is_active ? "active" : "inactive"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="instances">
          <Card>
            <CardHeader>
              <CardTitle>Strategy instances</CardTitle>
              <CardDescription>Live status. Kill any from here.</CardDescription>
            </CardHeader>
            <CardContent>
              {instances.isLoading ? (
                <Skeleton className="h-24" />
              ) : (instances.data ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No instances.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {instances.data!.map((i) => (
                    <li key={i.id} className="flex items-center justify-between rounded-md border p-2">
                      <div>
                        <p className="font-medium">{i.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {i.strategy_code} · {i.broker_account_label}
                        </p>
                      </div>
                      <Badge variant={i.status === "running" ? "profit" : "outline"}>
                        {i.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="backtests">
          <Card>
            <CardHeader>
              <CardTitle>Recent backtests</CardTitle>
              <CardDescription>Latest 10 runs.</CardDescription>
            </CardHeader>
            <CardContent>
              {backtests.isLoading ? (
                <Skeleton className="h-24" />
              ) : (backtests.data ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No backtests yet.</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {backtests.data!.map((b) => (
                    <li key={b.id} className="flex items-center justify-between rounded-md border p-2">
                      <div>
                        <p className="font-medium">{b.strategy_code}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(b.created_at).toLocaleString()}
                        </p>
                      </div>
                      <span className="tabular-nums text-xs">
                        {b.net_profit != null ? b.net_profit.toFixed(2) : "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardHeader>
              <CardTitle>Audit trail</CardTitle>
              <CardDescription>Actions authored by this user.</CardDescription>
            </CardHeader>
            <CardContent>
              {audit.isLoading ? (
                <Skeleton className="h-24" />
              ) : (audit.data?.items ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No entries.</p>
              ) : (
                <ul className="space-y-2">
                  {audit.data!.items.map((entry) => (
                    <AuditLogEntry key={entry.id} entry={entry} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="consents">
          <Card>
            <CardHeader>
              <CardTitle>Consent log</CardTitle>
              <CardDescription>Versioned record of every consent.</CardDescription>
            </CardHeader>
            <CardContent>
              {consents.isLoading ? (
                <Skeleton className="h-24" />
              ) : (consents.data ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No consents recorded.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {consents.data!.map((c) => (
                    <li key={c.id} className="flex items-center justify-between rounded-md border p-3">
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
      </Tabs>
    </div>
  );
}
