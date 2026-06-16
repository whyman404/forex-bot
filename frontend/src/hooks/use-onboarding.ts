"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import { useMe } from "./use-me";
import { useBrokerAccounts } from "./use-broker-accounts";
import { useStrategyInstances } from "./use-strategy-instance";
import type { OnboardingState, OnboardingStep } from "@/types";

const STORAGE_KEY = "forex-bot.onboarding";

interface LocalState {
  step: OnboardingStep;
  skipped: boolean;
  completedAt?: string;
}

function readLocal(): LocalState {
  if (typeof window === "undefined") return { step: 1, skipped: false };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { step: 1, skipped: false };
    const parsed = JSON.parse(raw) as Partial<LocalState>;
    return {
      step: (parsed.step ?? 1) as OnboardingStep,
      skipped: parsed.skipped ?? false,
      ...(parsed.completedAt ? { completedAt: parsed.completedAt } : {}),
    };
  } catch {
    return { step: 1, skipped: false };
  }
}

function writeLocal(state: LocalState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

/**
 * Composite onboarding hook.
 * Strategy: prefer server-side `onboarding_step` on /users/me; fall back to
 * localStorage if absent so we keep the UX even before Atlas wires the field.
 */
export function useOnboarding() {
  const me = useMe();
  const brokers = useBrokerAccounts();
  const instances = useStrategyInstances();
  const update = useUpdateOnboarding();

  const [local, setLocal] = React.useState<LocalState>(() => readLocal());

  React.useEffect(() => {
    writeLocal(local);
  }, [local]);

  const derived: OnboardingState = React.useMemo(() => {
    const emailVerified = me.data?.is_email_verified ?? false;
    const totpEnabled = me.data?.totp_enabled ?? false;
    const brokerConnected = (brokers.data?.length ?? 0) > 0;
    const paperCreated = (instances.data?.length ?? 0) > 0;
    return {
      step: local.step,
      email_verified: emailVerified,
      totp_enabled: totpEnabled,
      broker_connected: brokerConnected,
      paper_instance_created: paperCreated,
      ...(local.completedAt ? { completed_at: local.completedAt } : {}),
    };
  }, [me.data, brokers.data, instances.data, local]);

  const goTo = React.useCallback(
    (step: OnboardingStep) => {
      setLocal((s) => ({ ...s, step }));
      void update.mutateAsync({ step }).catch(() => {
        /* server route is optional; ignore failure */
      });
    },
    [update],
  );

  const complete = React.useCallback(() => {
    const completedAt = new Date().toISOString();
    setLocal({ step: 4, skipped: false, completedAt });
    void update.mutateAsync({ step: 4, completed: true }).catch(() => {
      /* ignore */
    });
  }, [update]);

  const skip = React.useCallback(() => {
    setLocal((s) => ({ ...s, skipped: true }));
    void update.mutateAsync({ skipped: true }).catch(() => {
      /* ignore */
    });
  }, [update]);

  const isVisible = !local.skipped && !local.completedAt;

  return {
    state: derived,
    step: local.step,
    isVisible,
    goTo,
    complete,
    skip,
    isLoading: me.isLoading || brokers.isLoading || instances.isLoading,
  };
}

export function useUpdateOnboarding() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (patch: { step?: OnboardingStep; completed?: boolean; skipped?: boolean }) => {
      try {
        return await api.patch<{ message: string }, typeof patch>(
          "/users/me/onboarding",
          patch,
          { token },
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // Endpoint not wired — localStorage fallback already took effect.
          return { message: "stored locally" };
        }
        throw err;
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}
