"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";
import { LogOut, Menu, ShieldAlert, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { ThemeToggle } from "@/components/theme-toggle";
import { useUiStore } from "@/store/ui";
import { useKillSwitchStore } from "@/store/kill-switch";
import { KillSwitchModal } from "@/components/kill-switch-modal";

export function AppTopbar() {
  const { data: session } = useSession();
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const killActive = useKillSwitchStore((s) => s.active);
  const [killOpen, setKillOpen] = React.useState(false);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Toggle sidebar"
          onClick={toggleSidebar}
          className="md:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {killActive && (
          <Badge variant="destructive" className="hidden sm:inline-flex">
            Kill switch active
          </Badge>
        )}

        <Button
          type="button"
          variant={killActive ? "destructive" : "outline"}
          size="sm"
          onClick={() => setKillOpen(true)}
          aria-label="Open kill switch"
          className="gap-1.5"
        >
          <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Kill switch</span>
        </Button>

        <ThemeToggle />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open user menu">
              <UserIcon className="h-4 w-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-sm font-semibold">{session?.user?.name ?? "Guest"}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {session?.user?.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => signOut({ callbackUrl: "/login" })}>
              <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <KillSwitchModal open={killOpen} onOpenChange={setKillOpen} />
    </header>
  );
}
