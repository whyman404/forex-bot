"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowLeftCircle,
  BellRing,
  ClipboardList,
  CreditCard,
  Megaphone,
  Settings2,
  ShieldAlert,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: typeof Users;
  destructive?: boolean;
};

const NAV: readonly NavItem[] = [
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/audit-log", label: "Audit Log", icon: ClipboardList },
  { href: "/admin/system", label: "System", icon: Settings2 },
  { href: "/admin/strategies", label: "Strategies", icon: BellRing },
  { href: "/admin/subscriptions", label: "Subscriptions", icon: CreditCard },
  { href: "/admin/notifications", label: "Broadcast", icon: Megaphone },
  { href: "/admin/system/global-kill", label: "Global Kill", icon: ShieldAlert, destructive: true },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <aside
      aria-label="Admin navigation"
      className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-destructive/30 bg-card md:flex md:flex-col"
    >
      <div className="flex h-14 items-center gap-2 border-b border-destructive/30 px-4">
        <ShieldAlert className="h-5 w-5 text-destructive" aria-hidden="true" />
        <span className="text-sm font-semibold">Admin Panel</span>
      </div>
      <nav className="flex-1 space-y-1 p-2" aria-label="Admin main">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active && item.destructive
                  ? "bg-destructive/15 text-destructive"
                  : active
                    ? "bg-accent text-accent-foreground"
                    : item.destructive
                      ? "text-destructive hover:bg-destructive/10"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-destructive/30 p-2">
        <Link
          href="/dashboard"
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent/50 hover:text-foreground"
        >
          <ArrowLeftCircle className="h-4 w-4" aria-hidden="true" />
          Back to app
        </Link>
      </div>
    </aside>
  );
}
