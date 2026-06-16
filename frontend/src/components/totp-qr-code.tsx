"use client";

import * as React from "react";
import QRCode from "qrcode";

interface TotpQrCodeProps {
  uri: string;
  size?: number;
}

/**
 * Renders the TOTP provisioning URI as an inline SVG QR.
 * Uses the `qrcode` npm package (no DOM canvas, server-renderable).
 */
export function TotpQrCode({ uri, size = 192 }: TotpQrCodeProps) {
  const [dataUrl, setDataUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(uri, {
      width: size,
      margin: 1,
      color: { dark: "#0f172a", light: "#ffffff" },
    })
      .then((url) => {
        if (!cancelled) setDataUrl(url);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to render QR");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [uri, size]);

  if (error) {
    return (
      <p role="alert" className="text-xs text-destructive">
        {error}
      </p>
    );
  }

  if (!dataUrl) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading QR code"
        className="animate-pulse rounded-md bg-muted"
        style={{ width: size, height: size }}
      />
    );
  }

  // eslint-disable-next-line @next/next/no-img-element
  return (
    <img
      src={dataUrl}
      alt="Two-factor authentication QR code"
      width={size}
      height={size}
      className="rounded-md border bg-white"
    />
  );
}
