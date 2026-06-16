"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { UserTable } from "@/components/admin/user-table";
import { useAdminUsers } from "@/hooks/admin/use-admin-users";
import type { UserRole, UserStatus } from "@/types/admin";
import type { SubscriptionPlan } from "@/types/domain";

const PER_PAGE = 25;

export default function AdminUsersPage() {
  const [q, setQ] = React.useState("");
  const [role, setRole] = React.useState<UserRole | "">("");
  const [status, setStatus] = React.useState<UserStatus | "">("");
  const [plan, setPlan] = React.useState<SubscriptionPlan | "">("");
  const [page, setPage] = React.useState(1);

  // Debounce search by 250ms.
  const [debouncedQ, setDebouncedQ] = React.useState(q);
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const query = {
    q: debouncedQ || undefined,
    role: role || undefined,
    status: status || undefined,
    plan: plan || undefined,
    page,
    per_page: PER_PAGE,
  };

  const { data, isLoading, error } = useAdminUsers(query);

  React.useEffect(() => setPage(1), [debouncedQ, role, status, plan]);

  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground">
          Search, filter, and manage user accounts. Destructive actions require 2FA step-up.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="users-search">Search</Label>
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  id="users-search"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="email or name"
                  className="pl-8"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="users-role">Role</Label>
              <select
                id="users-role"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole | "")}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">All</option>
                <option value="user">User</option>
                <option value="admin">Admin</option>
                <option value="support">Support</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="users-status">Status</Label>
              <select
                id="users-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as UserStatus | "")}
                className="h-10 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">All</option>
                <option value="active">Active</option>
                <option value="banned">Banned</option>
                <option value="pending_deletion">Pending deletion</option>
                <option value="deleted">Deleted</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="users-plan">Plan</Label>
              <select
                id="users-plan"
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
          </div>
        </CardContent>
      </Card>

      <UserTable
        users={data?.items ?? []}
        isLoading={isLoading}
        error={error as Error | null}
      />

      {data && data.total > PER_PAGE && (
        <div
          className="flex items-center justify-between text-sm text-muted-foreground"
          aria-live="polite"
        >
          <span>
            Page {data.page} of {totalPages} — {data.total.toLocaleString()} total users
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
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
