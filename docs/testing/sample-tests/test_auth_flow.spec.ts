/**
 * test_auth_flow.spec.ts
 *
 * Canonical Playwright E2E for the auth journey:
 *   signup -> verify email -> login -> 2FA enroll -> logout -> login (TOTP) -> me
 *
 * Why this file exists
 * --------------------
 * Auth is the gate to user funds. If signup or login are broken, no one trades.
 * If 2FA is silently bypassable, accounts get drained. This spec is part of the
 * release gate (release-checklist.md §1.E2E).
 *
 * Conventions
 * - No `page.waitForTimeout()`. Wait on conditions.
 * - Each test owns a unique email; tests run in parallel.
 * - Mailpit captures emails. Stripe is in test mode (unused here).
 *
 * Owner: Themis Saori
 */
import { test, expect, Page } from "@playwright/test";
import { authenticator } from "otplib";
import { fetchLatestVerificationLink, fetchLatestResetLink } from "./helpers/mailpit";
import { uniqueEmail } from "./helpers/factory";

const STRONG_PW = "Th3m!s-Saori-Tests-2026";

async function fillSignup(page: Page, email: string, password: string) {
  await page.goto("/signup");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel(/confirm password/i).fill(password);
  await page.getByRole("button", { name: /create account/i }).click();
}

test.describe("Auth — signup + verify + login", () => {
  test("happy path: signup -> verify email -> trial dashboard", async ({ page, context }) => {
    const email = uniqueEmail("signup-happy");
    await fillSignup(page, email, STRONG_PW);

    await expect(page.getByText(/check your inbox/i)).toBeVisible();

    const verifyUrl = await fetchLatestVerificationLink(email);
    expect(verifyUrl, "verification link from Mailpit").toMatch(/^https?:\/\//);

    const verifyPage = await context.newPage();
    await verifyPage.goto(verifyUrl);
    await expect(verifyPage).toHaveURL(/\/dashboard/);
    await expect(verifyPage.getByText(/14 days remaining/i)).toBeVisible();
    await expect(verifyPage.getByText(/trial/i)).toBeVisible();
  });

  test("blocks weak password without submission", async ({ page }) => {
    await page.goto("/signup");
    await page.getByLabel(/email/i).fill("weak@example.com");
    await page.getByLabel("Password", { exact: true }).fill("password");
    await page.getByLabel(/confirm password/i).fill("password");
    const button = page.getByRole("button", { name: /create account/i });
    await expect(button).toBeDisabled();
    await expect(page.getByText(/at least one uppercase|number|symbol/i)).toBeVisible();
  });

  test("duplicate email is generic, no enumeration leak", async ({ page, request }) => {
    const email = uniqueEmail("dup");
    // Pre-seed via API
    const res = await request.post("/api/auth/signup", {
      data: { email, password: STRONG_PW },
    });
    expect(res.status()).toBe(201);

    await fillSignup(page, email, STRONG_PW);
    // Friendly + generic; no "user exists" wording (avoid enumeration)
    await expect(page.getByRole("alert")).toContainText(/could not create account|try logging in/i);
  });

  test("verification link expired -> resend works", async ({ page, request }) => {
    const email = uniqueEmail("verify-expired");
    const res = await request.post("/api/auth/signup", {
      data: { email, password: STRONG_PW },
    });
    expect(res.status()).toBe(201);

    // Force expire in test env (test-only endpoint)
    await request.post("/api/_test/expire-verification-token", { data: { email } });

    const verifyUrl = await fetchLatestVerificationLink(email);
    await page.goto(verifyUrl);
    await expect(page.getByText(/link has expired/i)).toBeVisible();
    await page.getByRole("button", { name: /resend/i }).click();
    await expect(page.getByText(/new link sent/i)).toBeVisible();
  });
});

test.describe("Auth — login", () => {
  test("login redirects to dashboard and sets httpOnly refresh cookie", async ({ page, request, context }) => {
    const email = uniqueEmail("login-ok");
    await request.post("/api/_test/create-verified-user", {
      data: { email, password: STRONG_PW },
    });

    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(STRONG_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    const cookies = await context.cookies();
    const refresh = cookies.find((c) => c.name === "refresh_token");
    expect(refresh, "refresh_token cookie present").toBeDefined();
    expect(refresh!.httpOnly).toBe(true);
    expect(refresh!.secure).toBe(true);
    expect(["Lax", "Strict"]).toContain(refresh!.sameSite);
  });

  test("wrong password: generic error, no PII leak", async ({ page, request }) => {
    const email = uniqueEmail("login-bad");
    await request.post("/api/_test/create-verified-user", {
      data: { email, password: STRONG_PW },
    });

    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill("wrong-password-xxxxx");
    await page.getByRole("button", { name: /^sign in$/i }).click();

    const alert = page.getByRole("alert");
    await expect(alert).toContainText(/invalid credentials/i);
    await expect(alert).not.toContainText(email);
    await expect(alert).not.toContainText(/password/i);
  });

  test("lockout after 5 failed attempts", async ({ page, request }) => {
    const email = uniqueEmail("lockout");
    await request.post("/api/_test/create-verified-user", {
      data: { email, password: STRONG_PW },
    });

    await page.goto("/login");
    for (let i = 0; i < 5; i++) {
      await page.getByLabel(/email/i).fill(email);
      await page.getByLabel("Password", { exact: true }).fill("nope-" + i);
      await page.getByRole("button", { name: /^sign in$/i }).click();
      await expect(page.getByRole("alert")).toBeVisible();
    }
    // 6th try must show lockout
    await page.getByLabel("Password", { exact: true }).fill("nope-final");
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page.getByRole("alert")).toContainText(/locked|try again in/i);
  });
});

test.describe("Auth — 2FA enrollment and verification", () => {
  test("enroll TOTP, logout, login with TOTP", async ({ page, request, context }) => {
    const email = uniqueEmail("2fa");
    await request.post("/api/_test/create-verified-user", {
      data: { email, password: STRONG_PW },
    });
    // login
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(STRONG_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    // enroll
    await page.goto("/settings/security");
    await page.getByRole("button", { name: /enable 2fa/i }).click();
    const secret = await page.getByTestId("totp-secret").textContent();
    expect(secret, "TOTP secret shown once during enrollment").toBeTruthy();

    const code1 = authenticator.generate(secret!.trim());
    await page.getByLabel(/enter code/i).fill(code1);
    await page.getByRole("button", { name: /verify/i }).click();
    await expect(page.getByText(/two-factor authentication is on/i)).toBeVisible();

    // Backup codes shown once
    const backup = await page.getByTestId("backup-codes").innerText();
    expect(backup.split("\n").filter(Boolean)).toHaveLength(10);

    // logout
    await page.getByRole("button", { name: /account/i }).click();
    await page.getByRole("menuitem", { name: /log out/i }).click();
    await expect(page).toHaveURL(/\/login/);

    // login again -> TOTP prompt
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(STRONG_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/login\/2fa/);

    const code2 = authenticator.generate(secret!.trim());
    await page.getByLabel(/^code$/i).fill(code2);
    await page.getByRole("button", { name: /verify/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("invalid TOTP is rejected, account locked after 5", async ({ page, request }) => {
    const email = uniqueEmail("2fa-bad");
    await request.post("/api/_test/create-verified-user-with-2fa", {
      data: { email, password: STRONG_PW, totp_secret: "JBSWY3DPEHPK3PXP" },
    });

    await page.goto("/login");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(STRONG_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/login\/2fa/);

    for (let i = 0; i < 5; i++) {
      await page.getByLabel(/^code$/i).fill("000000");
      await page.getByRole("button", { name: /verify/i }).click();
      await expect(page.getByRole("alert")).toBeVisible();
    }
    await page.getByLabel(/^code$/i).fill("000000");
    await page.getByRole("button", { name: /verify/i }).click();
    await expect(page.getByRole("alert")).toContainText(/temporarily locked/i);
  });
});

test.describe("Auth — password reset", () => {
  test("reset link works once; old password invalidated", async ({ page, request }) => {
    const email = uniqueEmail("reset");
    await request.post("/api/_test/create-verified-user", {
      data: { email, password: STRONG_PW },
    });

    await page.goto("/login");
    await page.getByRole("link", { name: /forgot password/i }).click();
    await page.getByLabel(/email/i).fill(email);
    await page.getByRole("button", { name: /send reset link/i }).click();
    await expect(page.getByText(/if an account exists/i)).toBeVisible();

    const resetUrl = await fetchLatestResetLink(email);
    await page.goto(resetUrl);

    const NEW_PW = "Brand-New-P@ssw0rd-2026";
    await page.getByLabel("New password", { exact: true }).fill(NEW_PW);
    await page.getByLabel(/confirm/i).fill(NEW_PW);
    await page.getByRole("button", { name: /update password/i }).click();
    await expect(page).toHaveURL(/\/login/);

    // Old password rejected
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(STRONG_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page.getByRole("alert")).toContainText(/invalid credentials/i);

    // New password accepted
    await page.getByLabel("Password", { exact: true }).fill(NEW_PW);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    // Reused reset link rejected
    await page.context().clearCookies();
    await page.goto(resetUrl);
    await expect(page.getByText(/link is invalid or has been used/i)).toBeVisible();
  });
});
