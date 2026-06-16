"use client";

import * as React from "react";
import { toast } from "sonner";
import { Gift } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAdminCancelSubscription,
  useAdminGrantSubscription,
  useAdminSubscriptions,
} from "@/hooks/admin/use-admin-subscriptions";
import { ApiError } from "@/lib/api";
import type { SubscriptionPlan, SubscriptionStatus } from "@/types/domain";

export default function AdminSubscriptionsPage() {
  const [plan, setPlan] = React.useState<SubscriptionPlan | "">("");
  const [status, setStatus] = React.useState<SubscriptionStatus | "">("");
  const [page, setPage] = React.useState(1);
  const subs = useAdminSubscriptions({
    plan: plan || undefined,
    status: status || undefined,
    page,
    per_page: 25,
  });

  const cancel = useAdminCancelSubscription();
  const grant = useAdminGrantSubscription();

  const [cancelTarget, setCancelTarget] = React.useState<{ id: string; user_email: string } | null>(null);
  const [cancelReason, setCancelReason] = React.useState("");
  const [grantOpen, setGrantOpen] = React.useState(false);
  const [grantUser, setGrantUser] = React.useState("");
  const [grantPlan, setGrantPlan] = React.useState<SubscriptionPlan>("pro");
  const [grantDays, setGrantDays] = React.useState("30");
  const [grantReason, setGrantReason] = React.useState("");

  async function handleCancel() {
    if (!cancelTarget) return;
    if (cancelReason.trim().length < 3) {
      toast.error("Reason required.");
      return;
    }
    try {
      await cancel.mutateAsync({ id: cancelTarget.id, reason: cancelReason.trim() });
      toast.success(`Cancelled subscription for ${cancelTarget.user_email}.`);
      setCancelTarget(null);
      setCancelReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Cancel failed");
    }
  }

  async function handleGrant() {
    if (grantUser.trim().length === 0 || grantReason.trim().length < 3) {
      toast.error("User and reason required.");
      return;
    }
    try {
      const duration = grantDays === "lifetime" ? null : Number(grantDays);
      await grant.mutateAsync({
        user_id: grantUser.trim(),
        plan: grantPlan,
        duration_days: duration,
        reason: grantReason.trim(),
      });
      toast.success("Subscription granted.");
      setGrantOpen(false);
      setGrantUser("");
      setGrantReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Grant failed");
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Subscriptions</h1>
          <p className="text-sm text-muted-foreground">
            View Stripe-backed subscriptions, cancel, or grant manually.
          </p>
        </div>
        <Button variant="brand" onClick={() => setGrantOpen(true)}>
          <Gift className="mr-2 h-4 w-4" aria-hidden="true" /> Grant subscription
        </Button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sub-plan">Plan</Label>
              <select
                id="sub-plan"
                value={plan}
                onChange={(e) => setPlan(e.target.value as SubscriptionPlan | "")}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">All</option>
                <option value="free">Free</option>
                <option value="trial">Trial</option>
                <option value="pro">Pro</option>
                <option value="enterprise">Enterprise</option>
                <option value="lifetime">Lifetime</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sub-status">Status</Label>
              <select
                id="sub-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as SubscriptionStatus | "")}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">All</option>
                <option value="inactive">Inactive</option>
                <option value="trialing">Trialing</option>
                <option value="active">Active</option>
                <option value="past_due">Past due</option>
                <option value="canceled">Canceled</option>
                <option value="unpaid">Unpaid</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {subs.isLoading ? (
        <Skeleton className="h-64" />
      ) : (subs.data?.items ?? []).length === 0 ? (
        <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          No subscriptions match.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Period end</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-24 text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subs.data!.items.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>{s.user_email}</TableCell>
                  <TableCell>{s.plan}</TableCell>
                  <TableCell>
                    <Badge variant={s.status === "active" ? "profit" : "outline"}>
                      {s.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    ${(s.amount_cents / 100).toFixed(2)} {s.currency.toUpperCase()}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {s.current_period_end
                      ? new Date(s.current_period_end).toLocaleDateString()
                      : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(s.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setCancelTarget({ id: s.id, user_email: s.user_email })
                      }
                      disabled={s.status === "canceled"}
                    >
                      Cancel
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {subs.data && subs.data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span aria-live="polite">
            Page {subs.data.page} of {subs.data.total_pages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= subs.data.total_pages}
              onClick={() => setPage((p) => Math.min(subs.data!.total_pages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel subscription</DialogTitle>
            <DialogDescription>
              Cancels at period end (Stripe). User keeps access until then.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="cancel-reason">Reason (required, logged)</Label>
            <Input
              id="cancel-reason"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              autoComplete="off"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)}>
              Back
            </Button>
            <Button
              variant="destructive"
              onClick={handleCancel}
              disabled={cancel.isPending || cancelReason.trim().length < 3}
            >
              {cancel.isPending ? "Cancelling…" : "Confirm cancel"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={grantOpen} onOpenChange={setGrantOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Grant subscription</DialogTitle>
            <DialogDescription>
              Manually grant a plan without charging. Use for comps, refunds, or QA.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="grant-user">User ID or email</Label>
              <Input
                id="grant-user"
                value={grantUser}
                onChange={(e) => setGrantUser(e.target.value)}
                placeholder="uuid or email"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-plan">Plan</Label>
              <select
                id="grant-plan"
                value={grantPlan}
                onChange={(e) => setGrantPlan(e.target.value as SubscriptionPlan)}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="trial">Trial</option>
                <option value="pro">Pro</option>
                <option value="enterprise">Enterprise</option>
                <option value="lifetime">Lifetime</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-days">Duration</Label>
              <select
                id="grant-days"
                value={grantDays}
                onChange={(e) => setGrantDays(e.target.value)}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="14">14 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
                <option value="lifetime">Lifetime</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grant-reason">Reason (required, logged)</Label>
              <Input
                id="grant-reason"
                value={grantReason}
                onChange={(e) => setGrantReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGrantOpen(false)}>
              Cancel
            </Button>
            <Button variant="brand" onClick={handleGrant} disabled={grant.isPending}>
              {grant.isPending ? "Granting…" : "Grant"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
