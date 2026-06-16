"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditLogEntry } from "@/components/admin/audit-log-entry";
import {
  adminAuditLogCsvUrl,
  useAdminAuditLog,
} from "@/hooks/admin/use-admin-audit-log";
import { useSessionToken } from "@/hooks/use-session-token";
import { apiBaseUrl } from "@/lib/api";
import { toast } from "sonner";

export default function AdminAuditLogPage() {
  const [actor, setActor] = React.useState("");
  const [action, setAction] = React.useState("");
  const [targetType, setTargetType] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [page, setPage] = React.useState(1);

  const query = {
    actor: actor || undefined,
    action: action || undefined,
    target_type: targetType || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page,
    per_page: 50,
  };

  const { data, isLoading, error } = useAdminAuditLog(query);
  const { token } = useSessionToken();

  async function handleExport() {
    if (!token) {
      toast.error("Sign-in required.");
      return;
    }
    try {
      const res = await fetch(`${apiBaseUrl()}${adminAuditLogCsvUrl(query)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Audit log</h1>
          <p className="text-sm text-muted-foreground">
            Chronological record of admin and user actions.
          </p>
        </div>
        <Button variant="outline" onClick={handleExport}>
          <Download className="mr-2 h-4 w-4" aria-hidden="true" /> Export CSV
        </Button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-5">
            <div className="space-y-1.5">
              <Label htmlFor="al-actor">Actor</Label>
              <Input
                id="al-actor"
                placeholder="email or id"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="al-action">Action</Label>
              <Input
                id="al-action"
                placeholder="user.ban, login…"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="al-target">Target type</Label>
              <Input
                id="al-target"
                placeholder="user, subscription…"
                value={targetType}
                onChange={(e) => setTargetType(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="al-from">From</Label>
              <Input
                id="al-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="al-to">To</Label>
              <Input
                id="al-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {(error as Error).message}
        </div>
      ) : isLoading ? (
        <Skeleton className="h-64" />
      ) : (data?.items ?? []).length === 0 ? (
        <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          No entries match.
        </p>
      ) : (
        <ul className="space-y-2">
          {data!.items.map((entry) => (
            <AuditLogEntry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span aria-live="polite">
            Page {data.page} of {data.total_pages} · {data.total.toLocaleString()} entries
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
              disabled={page >= data.total_pages}
              onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
