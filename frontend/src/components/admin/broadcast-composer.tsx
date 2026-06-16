"use client";

import * as React from "react";
import { Mail, MessageSquare, Send } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useAdminBroadcastEstimate,
  useAdminSendBroadcast,
} from "@/hooks/admin/use-admin-broadcast";
import { TotpStepUpModal } from "./totp-step-up-modal";
import { ApiError } from "@/lib/api";
import type {
  BroadcastAudience,
  BroadcastChannel,
  BroadcastRequest,
  UserRole,
} from "@/types/admin";
import type { SubscriptionPlan } from "@/types/domain";

export function BroadcastComposer() {
  const [audience, setAudience] = React.useState<BroadcastAudience>("active");
  const [audienceRole, setAudienceRole] = React.useState<UserRole>("user");
  const [audiencePlan, setAudiencePlan] = React.useState<SubscriptionPlan>("pro");
  const [channel, setChannel] = React.useState<BroadcastChannel>("in_app");
  const [title, setTitle] = React.useState("");
  const [body, setBody] = React.useState("");
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [stepUpOpen, setStepUpOpen] = React.useState(false);

  const send = useAdminSendBroadcast();

  const composedRequest: BroadcastRequest = React.useMemo(
    () => ({
      audience,
      audience_role: audience === "role" ? audienceRole : undefined,
      audience_plan: audience === "plan" ? audiencePlan : undefined,
      channel,
      title,
      body,
    }),
    [audience, audienceRole, audiencePlan, channel, title, body],
  );

  const estimate = useAdminBroadcastEstimate(
    title.trim().length > 0 && body.trim().length > 0 ? composedRequest : null,
  );

  function openConfirm() {
    if (title.trim().length < 3) {
      toast.error("Title required (min 3 chars).");
      return;
    }
    if (body.trim().length < 10) {
      toast.error("Body must be at least 10 characters.");
      return;
    }
    setConfirmOpen(true);
  }

  async function handleSend(stepUpToken?: string) {
    try {
      const res = await send.mutateAsync({ body: composedRequest, stepUpToken });
      toast.success(`Broadcast queued to ${res.audience_count} recipients.`);
      setTitle("");
      setBody("");
      setConfirmOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Broadcast failed");
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Compose broadcast</CardTitle>
          <CardDescription>
            Notifications reach real people. Preview the audience count and review microcopy before
            sending.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Audience</legend>
            <div className="flex flex-wrap gap-2">
              {(["all", "active", "role", "plan"] as const).map((a) => (
                <label
                  key={a}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs ${
                    audience === a
                      ? "border-primary bg-primary/10"
                      : "border-input hover:bg-accent"
                  }`}
                >
                  <input
                    type="radio"
                    name="audience"
                    value={a}
                    checked={audience === a}
                    onChange={() => setAudience(a)}
                    className="sr-only"
                  />
                  {a}
                </label>
              ))}
            </div>
            {audience === "role" && (
              <div className="space-y-1.5">
                <Label htmlFor="aud-role" className="text-xs">
                  Role
                </Label>
                <select
                  id="aud-role"
                  value={audienceRole}
                  onChange={(e) => setAudienceRole(e.target.value as UserRole)}
                  className="h-9 w-40 rounded-md border bg-background px-2 text-sm"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                  <option value="support">support</option>
                </select>
              </div>
            )}
            {audience === "plan" && (
              <div className="space-y-1.5">
                <Label htmlFor="aud-plan" className="text-xs">
                  Plan
                </Label>
                <select
                  id="aud-plan"
                  value={audiencePlan}
                  onChange={(e) => setAudiencePlan(e.target.value as SubscriptionPlan)}
                  className="h-9 w-40 rounded-md border bg-background px-2 text-sm"
                >
                  <option value="free">free</option>
                  <option value="trial">trial</option>
                  <option value="pro">pro</option>
                  <option value="enterprise">enterprise</option>
                  <option value="lifetime">lifetime</option>
                </select>
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Channel</legend>
            <div className="flex gap-2">
              <label
                className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs ${
                  channel === "in_app" ? "border-primary bg-primary/10" : "border-input"
                }`}
              >
                <input
                  type="radio"
                  name="channel"
                  value="in_app"
                  checked={channel === "in_app"}
                  onChange={() => setChannel("in_app")}
                  className="sr-only"
                />
                <MessageSquare className="h-3 w-3" aria-hidden="true" /> In-app
              </label>
              <label
                className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs ${
                  channel === "email" ? "border-primary bg-primary/10" : "border-input"
                }`}
              >
                <input
                  type="radio"
                  name="channel"
                  value="email"
                  checked={channel === "email"}
                  onChange={() => setChannel("email")}
                  className="sr-only"
                />
                <Mail className="h-3 w-3" aria-hidden="true" /> Email
              </label>
            </div>
          </fieldset>

          <div className="space-y-1.5">
            <Label htmlFor="bc-title">Title</Label>
            <Input
              id="bc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bc-body">Body</Label>
            <textarea
              id="bc-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              maxLength={2000}
              className="w-full rounded-md border bg-background p-2 text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Plain text. Avoid panic-inducing language; recipients trust the inbox.
            </p>
          </div>

          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-muted-foreground" aria-live="polite">
              {estimate.data ? (
                <>
                  Audience size: <strong>{estimate.data.audience_count.toLocaleString()}</strong>
                  {channel === "email" && (
                    <>
                      {" · "}
                      Est. cost ~ ${(estimate.data.estimated_cost_usd_cents / 100).toFixed(2)}
                    </>
                  )}
                </>
              ) : estimate.isLoading ? (
                "Estimating audience…"
              ) : (
                "Fill title + body to estimate audience."
              )}
            </div>
            <Button variant="brand" onClick={openConfirm} disabled={send.isPending}>
              <Send className="mr-2 h-4 w-4" aria-hidden="true" /> Send
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm broadcast</DialogTitle>
            <DialogDescription>
              You are about to send a {channel === "email" ? "transactional email" : "in-app notification"} to{" "}
              <strong>{estimate.data?.audience_count.toLocaleString() ?? "?"}</strong> users. This is
              logged.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-md border p-3 text-sm">
            <div className="font-medium">{title}</div>
            <p className="whitespace-pre-wrap text-muted-foreground">{body}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="brand"
              onClick={() => {
                if (channel === "email" && (estimate.data?.audience_count ?? 0) > 1000) {
                  // Step-up required for large email blasts.
                  setStepUpOpen(true);
                } else {
                  void handleSend();
                }
              }}
              disabled={send.isPending}
            >
              {send.isPending ? "Sending…" : "Confirm & send"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TotpStepUpModal
        open={stepUpOpen}
        onOpenChange={setStepUpOpen}
        action="Send large broadcast"
        onSuccess={(token) => {
          void handleSend(token);
        }}
      />
    </>
  );
}
