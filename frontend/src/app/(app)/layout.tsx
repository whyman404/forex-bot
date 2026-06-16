"use client";

import * as React from "react";
import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { RiskDisclaimerModal } from "@/components/risk-disclaimer-modal";

export default function AppLayout({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <div className="flex min-h-dvh">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <main id="main" className="flex-1 p-4 md:p-6">
          {children}
        </main>
      </div>
      {/* Auto-opens once per consent version on first signin. */}
      <RiskDisclaimerModal triggerOnMount />
    </div>
  );
}
