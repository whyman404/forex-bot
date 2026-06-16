import { create } from "zustand";
import { persist } from "zustand/middleware";

interface KillSwitchState {
  active: boolean;
  reason: string | null;
  triggeredAt: string | null;
  trigger: (reason: string) => void;
  reset: () => void;
}

/**
 * Local UI-only kill-switch flag. The "real" stop lives at the server level —
 * each strategy instance can be killed via POST /strategy-instances/{id}/kill.
 * This store simply gives the top bar a sticky visual cue after the user has
 * killed at least one instance.
 */
export const useKillSwitchStore = create<KillSwitchState>()(
  persist(
    (set) => ({
      active: false,
      reason: null,
      triggeredAt: null,
      trigger: (reason) =>
        set({ active: true, reason, triggeredAt: new Date().toISOString() }),
      reset: () => set({ active: false, reason: null, triggeredAt: null }),
    }),
    { name: "forex-bot-kill-switch" },
  ),
);
