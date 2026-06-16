"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AdminAuditLogEntry } from "@/types/admin";

interface Props {
  entry: AdminAuditLogEntry;
}

const DESTRUCTIVE_PREFIXES = [
  "user.ban",
  "user.delete",
  "user.impersonate",
  "strategy.kill_all",
  "global_kill.engage",
];

function isDestructive(action: string): boolean {
  return DESTRUCTIVE_PREFIXES.some((p) => action.startsWith(p));
}

export function AuditLogEntry({ entry }: Props) {
  const [expanded, setExpanded] = React.useState(false);
  const hasPayload = entry.payload && Object.keys(entry.payload).length > 0;
  const date = new Date(entry.created_at);
  const dateStr = Number.isNaN(date.getTime()) ? entry.created_at : date.toLocaleString();
  const destructive = isDestructive(entry.action);

  return (
    <li
      className={cn(
        "rounded-md border bg-card text-sm",
        destructive && "border-destructive/30 bg-destructive/5",
      )}
    >
      <div className="flex items-start gap-3 p-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
          <User className="h-3.5 w-3.5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-medium">{entry.actor_email}</span>
            <span className="text-muted-foreground">performed</span>
            <Badge variant={destructive ? "destructive" : "outline"} className="font-mono text-[10px]">
              {entry.action}
            </Badge>
            {entry.target_label && (
              <>
                <span className="text-muted-foreground">on</span>
                <span className="font-mono text-xs">{entry.target_label}</span>
              </>
            )}
            {entry.impersonating_user_email && (
              <Badge variant="secondary" className="text-[10px]">
                as {entry.impersonating_user_email}
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <time dateTime={entry.created_at}>{dateStr}</time>
            {entry.ip_address && <span>IP {entry.ip_address}</span>}
            <span className="font-mono text-[10px]">{entry.target_type}</span>
          </div>
          {hasPayload && (
            <>
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                aria-expanded={expanded}
                aria-controls={`audit-payload-${entry.id}`}
              >
                {expanded ? (
                  <ChevronDown className="h-3 w-3" aria-hidden="true" />
                ) : (
                  <ChevronRight className="h-3 w-3" aria-hidden="true" />
                )}
                {expanded ? "Hide payload" : "Show payload"}
              </button>
              {expanded && (
                <pre
                  id={`audit-payload-${entry.id}`}
                  className="overflow-x-auto rounded-md bg-muted p-3 text-[11px] font-mono"
                >
                  {JSON.stringify(entry.payload, null, 2)}
                </pre>
              )}
            </>
          )}
        </div>
      </div>
    </li>
  );
}
