import Link from "next/link";
import { Gauge } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/30 px-4 py-12">
      <main id="main" className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-semibold"
            aria-label="Forex Bot home"
          >
            <Gauge className="h-6 w-6 text-brand" aria-hidden="true" />
            Forex Bot
          </Link>
        </div>
        {children}
      </main>
    </div>
  );
}
