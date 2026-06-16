"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface ParamField {
  key: string;
  label: string;
  type?: "number" | "text";
  step?: number;
  min?: number;
  max?: number;
  help?: string;
}

interface ParamsFormProps {
  fields: ParamField[];
  value: Record<string, number | string | boolean>;
  onChange: (value: Record<string, number | string | boolean>) => void;
  disabled?: boolean;
}

export function ParamsForm({ fields, value, onChange, disabled }: ParamsFormProps) {
  function handleChange(field: ParamField, raw: string) {
    const next = { ...value };
    next[field.key] = field.type === "number" ? Number(raw) : raw;
    onChange(next);
  }

  return (
    <fieldset disabled={disabled} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {fields.map((f) => {
        const v = value[f.key];
        const inputId = `param-${f.key}`;
        const helpId = f.help ? `${inputId}-help` : undefined;
        return (
          <div key={f.key} className="space-y-1.5">
            <Label htmlFor={inputId}>{f.label}</Label>
            <Input
              id={inputId}
              name={f.key}
              type={f.type ?? "number"}
              step={f.step}
              min={f.min}
              max={f.max}
              value={v === undefined ? "" : String(v)}
              onChange={(e) => handleChange(f, e.target.value)}
              aria-describedby={helpId}
              inputMode={f.type === "number" ? "decimal" : "text"}
            />
            {f.help && (
              <p id={helpId} className="text-xs text-muted-foreground">
                {f.help}
              </p>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}
