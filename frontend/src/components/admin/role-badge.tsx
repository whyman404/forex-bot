import { ShieldCheck, User, LifeBuoy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/admin";

const ROLE_VARIANTS: Record<
  UserRole,
  { label: string; variant: "default" | "destructive" | "secondary" | "outline"; icon: typeof User }
> = {
  user: { label: "User", variant: "outline", icon: User },
  admin: { label: "Admin", variant: "destructive", icon: ShieldCheck },
  support: { label: "Support", variant: "secondary", icon: LifeBuoy },
};

interface RoleBadgeProps {
  role: UserRole;
  className?: string;
}

export function RoleBadge({ role, className }: RoleBadgeProps) {
  const v = ROLE_VARIANTS[role] ?? ROLE_VARIANTS.user;
  const Icon = v.icon;
  return (
    <Badge
      variant={v.variant}
      className={cn("gap-1", className)}
      role="status"
      aria-label={`Role: ${v.label}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {v.label}
    </Badge>
  );
}
