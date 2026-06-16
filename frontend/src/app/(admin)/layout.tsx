"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { AdminSidebar } from "@/components/admin/admin-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Admin layout. Red accent + warning bar to signal the danger context.
 *
 * Role gate:
 *   - Middleware already redirects non-admins on the edge, but we double-check
 *     client-side as defence in depth. Without the check, a stale-token race
 *     could briefly render admin UI.
 *
 * The whole subtree gets `data-admin` so global CSS can apply a danger accent.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const isAdmin = session?.user?.isAdmin === true;

  React.useEffect(() => {
    if (status === "authenticated" && !isAdmin) {
      toast.error("Admin access required.");
      router.replace("/dashboard");
    }
  }, [status, isAdmin, router]);

  if (status === "loading" || (status === "authenticated" && !isAdmin)) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <Skeleton className="h-24 w-72" />
      </div>
    );
  }

  return (
    <div data-admin="true" className="flex min-h-dvh">
      <AdminSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <div
          role="alert"
          className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-xs font-medium text-destructive"
        >
          <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
          <span>ADMIN MODE — actions are logged and audited.</span>
        </div>
        <main id="main" className="flex-1 p-4 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
