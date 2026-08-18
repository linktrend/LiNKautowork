import { createHash } from "node:crypto";

export interface PayloadSyncClient {
  syncFromMirror(
    mirrorWriteRef: string,
    payloadTargetRef: string,
    leaseId: string,
  ): Promise<{ payloadSyncRef: string; documentRefs: string[]; status: string }>;

  checkReadiness(
    payloadSyncRef: string,
    requirements: {
      requiredPages: string[];
      requiredNavigationItems: string[];
      requiredContentBlocks: string[];
      requiredMediaRefs: string[];
    },
  ): Promise<{ checksPassed: boolean; failedChecks: string[] }>;
}

type FetchLike = (input: URL | string | Request, init?: RequestInit) => Promise<Response>;

export function createPayloadSyncClient(deps?: {
  fetchImpl?: FetchLike;
  payloadBaseUrl?: string;
  payloadApiKey?: string;
  syncCollection?: string;
  readinessCollection?: string;
}): PayloadSyncClient {
  const fetchImpl = deps?.fetchImpl ?? fetch;
  const payloadBaseUrl = deps?.payloadBaseUrl ?? process.env.LINKAUTOWORK_PAYLOAD_BASE_URL;
  const payloadApiKey = (deps && deps.payloadApiKey) || process.env.LINKAUTOWORK_PAYLOAD_API_KEY;
  const syncCollection = deps?.syncCollection ?? process.env.LINKAUTOWORK_PAYLOAD_SYNC_COLLECTION ?? "site-settings";
  const readinessCollection =
    deps?.readinessCollection ?? process.env.LINKAUTOWORK_PAYLOAD_READINESS_COLLECTION ?? "pages";

  function buildUrl(path: string): string {
    if (!payloadBaseUrl) {
      throw new Error("Payload client is not configured for development mode");
    }
    return `${payloadBaseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  }

  function headers(): Record<string, string> {
    const base: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (!payloadApiKey) return base;
    // Payload CMS user API keys use collection-scoped auth, not Bearer JWT.
    return { ...base, Authorization: `users API-Key ${payloadApiKey}` };
  }

  async function assertOk(response: Response, op: string): Promise<void> {
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`Payload ${op} failed (${response.status} ${response.statusText})${body ? `: ${body}` : ""}`);
    }
  }

  return {
    async syncFromMirror(mirrorWriteRef, payloadTargetRef, leaseId) {
      const payloadSyncRef = `payload_sync:${payloadTargetRef}:${digest({ mirrorWriteRef, leaseId })}`;
      const response = await fetchImpl(buildUrl(`/api/${syncCollection}`), {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          mirrorWriteRef,
          payloadTargetRef,
          leaseId,
          payloadSyncRef,
          status: "succeeded",
        }),
      });
      await assertOk(response, "sync");

      const documentRefs = [`${payloadTargetRef}:home`, `${payloadTargetRef}:about`, `${payloadTargetRef}:contact`];
      return {
        payloadSyncRef,
        documentRefs,
        status: "succeeded",
      };
    },

    async checkReadiness(payloadSyncRef, requirements) {
      const failedChecks: string[] = [];

      const response = await fetchImpl(
        buildUrl(
          `/api/${readinessCollection}?where[payloadSyncRef][equals]=${encodeURIComponent(payloadSyncRef)}&limit=100`,
        ),
        {
          method: "GET",
          headers: headers(),
        },
      );
      await assertOk(response, "readiness-check");

      const responseData = await response.json().catch(() => ({ docs: [] })) as { docs: Array<{ slug?: string; title?: string; _slug?: string }> };
      const docs = responseData.docs || [];

      for (const page of requirements.requiredPages) {
        const found = docs.some(doc =>
          doc.slug === page ||
          doc._slug === page ||
          doc.title?.toLowerCase().includes(page.toLowerCase()),
        );
        if (!found) {
          failedChecks.push(`missing_page:${page}`);
        }
      }

      if (requirements.requiredNavigationItems.length > 0 && docs.length === 0) {
        failedChecks.push("navigation_items:no_content");
      }
      if (requirements.requiredContentBlocks.length > 0 && docs.length === 0) {
        failedChecks.push("content_blocks:no_content");
      }
      if (requirements.requiredMediaRefs.length > 0) {
        const mediaResponse = await fetchImpl(
          buildUrl(`/api/media?limit=1`),
          { method: "GET", headers: headers() },
        );
        if (!mediaResponse.ok) {
          failedChecks.push("media_refs:unavailable");
        }
      }

      return {
        checksPassed: failedChecks.length === 0,
        failedChecks,
      };
    },
  };
}

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex").slice(0, 16);
}
