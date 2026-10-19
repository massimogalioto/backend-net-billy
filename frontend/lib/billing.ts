import { authUrl } from "@/components/AuthGate";

export type BillingStatus = {
  plan_code: string;
  plan_name: string;
  plan_status: string;
  stripe_status: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  payment_grace_until: string | null;
};

export type AccountUsage = {
  plan: { code: string; name: string };
  cte: { used: number; limit: number; remaining: number };
  comparisons: { used: number; limit: number; remaining: number; period: string };
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

export async function authenticatedJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(authUrl(path), { ...init, credentials: "include", cache: "no-store" });
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "Il servizio non è disponibile. Riprova tra poco.";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

export function startCheckout(plan: "START" | "TOP") {
  return authenticatedJson<{ checkout_url: string }>("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan }),
  });
}

export function openCustomerPortal() {
  return authenticatedJson<{ portal_url: string }>("/billing/portal", { method: "POST" });
}
