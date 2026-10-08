import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });
describe("collegamento statico", () => {
  it("indirizza upload e salvataggio al backend con cookie di sessione", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_MODE", "true");
    vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://backend.example/");
    const { connectionRequest } = await import("./connection");
    for (const endpoint of ["upload-cte", "salva-offerta", "salva-offerta-manuale", "upload-bolletta", "confronta"]) {
      const [url, init] = connectionRequest(`/api/service/${endpoint}`, { method: "POST" });
      expect(url).toBe(`https://backend.example/${endpoint}`);
      expect(new Headers(init.headers).get("x-api-key")).toBeNull();
      expect(init.credentials).toBe("include");
    }
  });
  it("mantiene il proxy quando si usa il server Next.js", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_MODE", "false");
    const { connectionRequest } = await import("./connection");
    expect(connectionRequest("/api/service/upload-cte", { method: "POST" })[0]).toBe("/api/service/upload-cte");
  });
});
