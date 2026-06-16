import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-3xl font-bold">404 — not found</h1>
      <p className="max-w-md text-muted-foreground">
        The page you&apos;re looking for has moved or never existed. Let&apos;s get you back.
      </p>
      <Button asChild variant="brand">
        <Link href="/">Take me home</Link>
      </Button>
    </div>
  );
}
