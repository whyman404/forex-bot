"use client";

import * as React from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { RoleBadge } from "./role-badge";
import { UserActionsMenu } from "./user-actions-menu";
import type { AdminUserListItem } from "@/types/admin";

interface Props {
  users: AdminUserListItem[];
  isLoading: boolean;
  error: Error | null;
}

function initials(emailOrName?: string | null): string {
  if (!emailOrName) return "?";
  const parts = emailOrName.replace(/@.*/, "").split(/[^a-zA-Z0-9]+/).filter(Boolean);
  const first = parts[0];
  const second = parts[1];
  if (first && second) return (first[0]! + second[0]!).toUpperCase();
  return first?.slice(0, 2).toUpperCase() ?? "?";
}

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

export function UserTable({ users, isLoading, error }: Props) {
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
      >
        {error.message}
      </div>
    );
  }

  if (isLoading) {
    return <Skeleton className="h-64" />;
  }

  if (users.length === 0) {
    return (
      <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        No users match your filters.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="w-12">
              <span className="sr-only">Avatar</span>
            </TableHead>
            <TableHead scope="col">User</TableHead>
            <TableHead scope="col">Role</TableHead>
            <TableHead scope="col">Status</TableHead>
            <TableHead scope="col">Sub</TableHead>
            <TableHead scope="col" className="text-right">
              Brokers
            </TableHead>
            <TableHead scope="col" className="text-right">
              Instances
            </TableHead>
            <TableHead scope="col">Last login</TableHead>
            <TableHead scope="col">Joined</TableHead>
            <TableHead scope="col" className="w-12 text-right">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell>
                <div
                  aria-hidden="true"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-medium"
                >
                  {initials(u.full_name ?? u.display_name ?? u.email)}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                  <Link
                    href={`/admin/users/${u.id}`}
                    className="text-sm font-medium underline-offset-4 hover:underline"
                  >
                    {u.full_name ?? u.display_name ?? u.email}
                  </Link>
                  <span className="text-xs text-muted-foreground">{u.email}</span>
                </div>
              </TableCell>
              <TableCell>
                <RoleBadge role={u.role} />
              </TableCell>
              <TableCell>
                <Badge variant={u.status === "banned" ? "destructive" : "outline"}>
                  {u.status}
                </Badge>
              </TableCell>
              <TableCell>
                {u.subscription_plan ? (
                  <span className="text-xs">
                    {u.subscription_plan}
                    <span className="ml-1 text-muted-foreground">· {u.subscription_status}</span>
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">{u.broker_count}</TableCell>
              <TableCell className="text-right tabular-nums">{u.instances_count}</TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {formatDate(u.last_login_at)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {formatDate(u.created_at)}
              </TableCell>
              <TableCell className="text-right">
                <UserActionsMenu user={{ id: u.id, email: u.email, status: u.status }} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
