"use client";

import * as React from "react";
import {
  Ban,
  Eye,
  KeyRound,
  MoreHorizontal,
  Pencil,
  ShieldOff,
  Trash2,
  UserCog,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TotpStepUpModal } from "./totp-step-up-modal";
import { ResetPasswordResultModal } from "./reset-password-result-modal";
import { ImpersonateModal } from "./impersonate-modal";
import {
  useAdminBanUser,
  useAdminDeleteUser,
  useAdminResetPassword,
  useAdminUnbanUser,
} from "@/hooks/admin/use-admin-users";
import { ApiError } from "@/lib/api";
import type { AdminUserListItem } from "@/types/admin";

interface Props {
  user: Pick<AdminUserListItem, "id" | "email" | "status">;
}

type StepUpIntent = "reset_password" | "impersonate" | "ban" | "delete" | null;

export function UserActionsMenu({ user }: Props) {
  const [stepUpIntent, setStepUpIntent] = React.useState<StepUpIntent>(null);
  const [stepUpToken, setStepUpToken] = React.useState<string | null>(null);
  const [impersonateOpen, setImpersonateOpen] = React.useState(false);
  const [resetOpen, setResetOpen] = React.useState(false);
  const [resetResult, setResetResult] = React.useState<{
    temp_password: string;
    expires_at: string;
  } | null>(null);
  const [banOpen, setBanOpen] = React.useState(false);
  const [banReason, setBanReason] = React.useState("");
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [deletePhrase, setDeletePhrase] = React.useState("");

  const resetPw = useAdminResetPassword();
  const ban = useAdminBanUser();
  const unban = useAdminUnbanUser();
  const del = useAdminDeleteUser();

  const deletePhraseRequired = `DELETE-${user.email}`;

  function requestStepUp(intent: NonNullable<StepUpIntent>) {
    setStepUpIntent(intent);
  }

  async function onStepUpSuccess(token: string) {
    setStepUpToken(token);
    if (stepUpIntent === "reset_password") {
      try {
        const res = await resetPw.mutateAsync({ id: user.id, stepUpToken: token });
        setResetResult({ temp_password: res.temp_password, expires_at: res.expires_at });
        setResetOpen(true);
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Reset failed");
      }
    } else if (stepUpIntent === "impersonate") {
      setImpersonateOpen(true);
    } else if (stepUpIntent === "ban") {
      setBanOpen(true);
    } else if (stepUpIntent === "delete") {
      setDeleteOpen(true);
    }
    setStepUpIntent(null);
  }

  async function handleBanConfirm() {
    if (!stepUpToken || banReason.trim().length < 3) {
      toast.error("Reason required, min 3 characters.");
      return;
    }
    try {
      await ban.mutateAsync({ id: user.id, reason: banReason.trim(), stepUpToken });
      toast.success("User banned.");
      setBanOpen(false);
      setBanReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Ban failed");
    }
  }

  async function handleUnban() {
    try {
      await unban.mutateAsync({ id: user.id });
      toast.success("User unbanned.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Unban failed");
    }
  }

  async function handleDeleteConfirm() {
    if (!stepUpToken || deletePhrase !== deletePhraseRequired) return;
    try {
      await del.mutateAsync({
        id: user.id,
        confirmation_phrase: deletePhrase,
        stepUpToken,
      });
      toast.success("User scheduled for deletion (30-day grace).");
      setDeleteOpen(false);
      setDeletePhrase("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Delete failed");
    }
  }

  const isBanned = user.status === "banned";

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Actions for ${user.email}`}>
            <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>Actions</DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link href={`/admin/users/${user.id}`}>
              <Eye className="mr-2 h-4 w-4" aria-hidden="true" /> View
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href={`/admin/users/${user.id}?edit=1`}>
              <Pencil className="mr-2 h-4 w-4" aria-hidden="true" /> Edit
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => requestStepUp("reset_password")}>
            <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" /> Reset password
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => requestStepUp("impersonate")}>
            <UserCog className="mr-2 h-4 w-4" aria-hidden="true" /> Impersonate
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {isBanned ? (
            <DropdownMenuItem onSelect={handleUnban}>
              <ShieldOff className="mr-2 h-4 w-4" aria-hidden="true" /> Unban
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              onSelect={() => requestStepUp("ban")}
              className="text-destructive focus:text-destructive"
            >
              <Ban className="mr-2 h-4 w-4" aria-hidden="true" /> Ban
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            onSelect={() => requestStepUp("delete")}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <TotpStepUpModal
        open={!!stepUpIntent}
        onOpenChange={(v) => !v && setStepUpIntent(null)}
        onSuccess={onStepUpSuccess}
        action={
          stepUpIntent === "reset_password"
            ? `Reset password for ${user.email}`
            : stepUpIntent === "impersonate"
              ? `Impersonate ${user.email}`
              : stepUpIntent === "ban"
                ? `Ban ${user.email}`
                : stepUpIntent === "delete"
                  ? `Delete ${user.email}`
                  : ""
        }
      />

      {resetResult && (
        <ResetPasswordResultModal
          open={resetOpen}
          onOpenChange={setResetOpen}
          tempPassword={resetResult.temp_password}
          expiresAt={resetResult.expires_at}
          userEmail={user.email}
        />
      )}

      {stepUpToken && (
        <ImpersonateModal
          open={impersonateOpen}
          onOpenChange={setImpersonateOpen}
          userId={user.id}
          userEmail={user.email}
          stepUpToken={stepUpToken}
        />
      )}

      <Dialog open={banOpen} onOpenChange={setBanOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ban {user.email}?</DialogTitle>
            <DialogDescription>
              They will be signed out everywhere. Active strategies will be paused. This is logged.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="ban-reason">Reason (required, logged)</Label>
            <Input
              id="ban-reason"
              value={banReason}
              onChange={(e) => setBanReason(e.target.value)}
              autoComplete="off"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBanOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleBanConfirm}
              disabled={ban.isPending || banReason.trim().length < 3}
            >
              {ban.isPending ? "Banning…" : "Ban user"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {user.email}?</DialogTitle>
            <DialogDescription>
              This is a 30-day soft delete. Stripe subscriptions will be canceled. Live engines will
              be killed. Type{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">{deletePhraseRequired}</code>{" "}
              to confirm.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="delete-phrase">Confirmation phrase</Label>
            <Input
              id="delete-phrase"
              value={deletePhrase}
              onChange={(e) => setDeletePhrase(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={del.isPending || deletePhrase !== deletePhraseRequired}
            >
              {del.isPending ? "Deleting…" : "Delete user"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
