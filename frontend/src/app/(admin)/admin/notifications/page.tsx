"use client";

import { BroadcastComposer } from "@/components/admin/broadcast-composer";

export default function AdminNotificationsPage() {
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Broadcast notifications</h1>
        <p className="text-sm text-muted-foreground">
          Compose, preview audience size, and send in-app or email broadcasts.
        </p>
      </header>
      <BroadcastComposer />
    </div>
  );
}
