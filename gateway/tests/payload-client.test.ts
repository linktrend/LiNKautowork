import { describe, expect, it, vi } from "vitest";
import { createPayloadSyncClient } from "../src/lib/payload-client.js";

describe("createPayloadSyncClient", () => {
  it("sends Payload users API-Key Authorization header (not Bearer)", async () => {
    const fetchImpl = vi.fn(async (_input: URL | string | Request, init?: RequestInit) => {
      return new Response(null, { status: 201 });
    });

    const client = createPayloadSyncClient({
      fetchImpl,
      payloadBaseUrl: "http://127.0.0.1:3001",
      payloadApiKey: "ltfx.ph.2e7a7ee14c.v1",
      syncCollection: "site-settings",
      readinessCollection: "pages",
    });

    await client.syncFromMirror("mirror:1", "site-1", "lease-1");

    expect(fetchImpl).toHaveBeenCalledOnce();
    const init = fetchImpl.mock.calls[0]?.[1];
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.Authorization).toBe("users API-Key ltfx.ph.2e7a7ee14c.v1");
    expect(headers?.Authorization ?? "").not.toMatch(/^Bearer /);
  });
});
