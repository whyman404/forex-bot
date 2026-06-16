"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step {
  id: number;
  label: string;
}

interface OnboardingStepperProps {
  steps: Step[];
  currentStep: number;
  completedSteps?: number[];
}

/**
 * Accessible 4-step progress indicator. Uses `<ol>` so the order is exposed
 * to assistive tech; current step is announced via `aria-current="step"`.
 */
export function OnboardingStepper({
  steps,
  currentStep,
  completedSteps = [],
}: OnboardingStepperProps): React.ReactElement {
  return (
    <nav aria-label="Onboarding progress">
      <ol className="flex w-full items-center gap-2 overflow-x-auto pb-1">
        {steps.map((step, idx) => {
          const isComplete = completedSteps.includes(step.id) || step.id < currentStep;
          const isCurrent = step.id === currentStep;
          return (
            <li key={step.id} className="flex flex-1 items-center gap-2">
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs",
                  isCurrent && "bg-brand text-brand-foreground",
                  isComplete && !isCurrent && "bg-profit/15 text-profit",
                  !isComplete && !isCurrent && "bg-muted text-muted-foreground",
                )}
                aria-current={isCurrent ? "step" : undefined}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold",
                    isCurrent && "bg-brand-foreground text-brand",
                    isComplete && !isCurrent && "bg-profit text-background",
                    !isComplete && !isCurrent && "bg-background text-muted-foreground",
                  )}
                >
                  {isComplete ? <Check className="h-3 w-3" aria-hidden="true" /> : step.id}
                </span>
                <span className="whitespace-nowrap font-medium">{step.label}</span>
              </div>
              {idx < steps.length - 1 ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    "hidden h-px flex-1 bg-border sm:block",
                    isComplete && "bg-profit/40",
                  )}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
