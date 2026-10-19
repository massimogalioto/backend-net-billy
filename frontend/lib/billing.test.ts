import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

describe("API billing", () => {
  it("avvia Checkout con piano e cookie di sessione", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_MODE", "true");
    vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://backend.example");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ checkout_url: "https://checkout.stripe.test/session" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { startCheckout } = await import("./billing");

    await expect(startCheckout("START")).resolves.toEqual({ checkout_url: "https://checkout.stripe.test/session" });
    expect(fetchMock).toHaveBeenCalledWith("https://backend.example/billing/checkout", expect.objectContaining({
      method: "POST", credentials: "include", body: JSON.stringify({ plan: "START" }),
    }));
  });

  it("apre il Customer Portal senza inviare dati del tenant", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_MODE", "true");
    vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://backend.example");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ portal_url: "https://billing.stripe.test/session" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { openCustomerPortal } = await import("./billing");

    await openCustomerPortal();
    expect(fetchMock).toHaveBeenCalledWith("https://backend.example/billing/portal", expect.objectContaining({
      method: "POST", credentials: "include",
    }));
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("body");
  });
});
