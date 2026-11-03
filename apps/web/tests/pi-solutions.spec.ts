import { expect, test } from "@playwright/test";
import {
  brainSolutionsService,
  isRollbackable,
  rejectReasonOk,
} from "../src/features/pi/brain-solutions-service";
import { bindApiWorkspace, errorMessage } from "../src/services/api-client";

type Call = { url: string; method: string; body: unknown };

async function withFetch<T>(
  reply: (call: Call) => { status?: number; body: unknown },
  run: (calls: Call[]) => Promise<T>,
) {
  const original = globalThis.fetch;
  const calls: Call[] = [];
  bindApiWorkspace("tenant-a", "environment-b");
  globalThis.fetch = async (input, options) => {
    const call: Call = {
      url: String(input),
      method: options?.method ?? "GET",
      body: options?.body ? JSON.parse(String(options.body)) : undefined,
    };
    calls.push(call);
    const r = reply(call);
    return new Response(JSON.stringify(r.body), { status: r.status ?? 200 });
  };
  try {
    return await run(calls);
  } finally {
    bindApiWorkspace(undefined, undefined);
    globalThis.fetch = original;
  }
}

const version = {
  version: "1.2",
  status: "live",
  changes: ["sample_reply"],
  evidence: { candidates: 3 },
  created_at: "2026-10-20T10:00:00Z",
  rolled_back_at: null,
};

test("solutions overview, detail and review parse the API shapes", async () => {
  await withFetch(
    ({ url }) => {
      if (url.endsWith("/pi/solutions"))
        return {
          body: {
            industries: [
              {
                industry: "dairy",
                seeded: true,
                latest: version,
                versions: 2,
              },
            ],
          },
        };
      if (url.endsWith("/pi/solutions/dairy"))
        return {
          body: {
            industry: "dairy",
            sample_reply: { person: "Milk is late", pi: "Which route?" },
            versions: [version],
            ideas: 4,
          },
        };
      return {
        body: {
          ideas: [
            {
              id: "a1",
              industry: "dairy",
              problem: "late_delivery",
              language: "en",
              text: "Offer a cold-chain check",
              kind: "process",
              status: "review",
              uses: 0,
              source: "learned",
              traffic_cap: 0.1,
              feedback: 0,
              retired_reason: "",
            },
          ],
          proposals: [
            { id: "p1", need: "Route planning", industries: [], count: 6 },
          ],
        },
      };
    },
    async (calls) => {
      const o = await brainSolutionsService.overview();
      expect(o.industries[0].latest.version).toBe("1.2");
      const d = await brainSolutionsService.detail("dairy");
      expect(d.sample_reply?.pi).toBe("Which route?");
      const r = await brainSolutionsService.review();
      expect(r.ideas[0].status).toBe("review");
      expect(r.proposals[0].count).toBe(6);
      expect(calls.map((c) => c.method)).toEqual(["GET", "GET", "GET"]);
    },
  );
});

test("ideas are filtered by industry and status in the query string", async () => {
  await withFetch(
    () => ({ body: { items: [] } }),
    async (calls) => {
      await brainSolutionsService.arms("dairy", "retired");
      await brainSolutionsService.arms();
      expect(calls[0].url).toContain(
        "/pi/solutions/arms?industry=dairy&status=retired",
      );
      expect(calls[1].url.endsWith("/pi/solutions/arms")).toBe(true);
    },
  );
});

test("decisions send approve and reason; rollback posts to the industry only", async () => {
  await withFetch(
    ({ url }) =>
      url.includes("/rollback")
        ? { body: { industry: "dairy", rolled_back: "1.2" } }
        : url.includes("/proposals/")
          ? { body: { id: "p1", status: "rejected" } }
          : {
              body: {
                id: "a1",
                industry: "dairy",
                text: "x",
                status: "retired",
              },
            },
    async (calls) => {
      await brainSolutionsService.decideIdea("a1", false, "touches pricing");
      await brainSolutionsService.decideProposal("p1", true);
      const done = await brainSolutionsService.rollback("dairy");
      expect(done.rolled_back).toBe("1.2");
      expect(calls[0].body).toEqual({
        approve: false,
        reason: "touches pricing",
      });
      expect(calls[1].body).toEqual({ approve: true, reason: "" });
      expect(calls[2].url.endsWith("/pi/solutions/dairy/rollback")).toBe(true);
      expect(calls[2].method).toBe("POST");
    },
  );
});

test("a rollback refused by the API surfaces the server message", async () => {
  await withFetch(
    () => ({
      status: 409,
      body: {
        error: {
          code: "NOTHING_TO_ROLL_BACK",
          request_id: "req-1",
          message: "This industry is already on its starting version",
        },
      },
    }),
    async () => {
      const error = await brainSolutionsService.rollback("dairy").then(
        () => null,
        (e: unknown) => e,
      );
      expect(error).not.toBeNull();
      expect(errorMessage(error)).toBe(
        "This industry is already on its starting version",
      );
    },
  );
});

test("rollback is only offered for a learned live or shadow version", () => {
  expect(isRollbackable({ version: "1.0", status: "live" })).toBe(false);
  expect(isRollbackable({ version: "1.2", status: "rolled_back" })).toBe(false);
  expect(isRollbackable({ version: "1.2", status: "live" })).toBe(true);
  expect(isRollbackable({ version: "1.3", status: "shadow" })).toBe(true);
});

test("rejecting needs a short reason", () => {
  expect(rejectReasonOk("")).toBe(false);
  expect(rejectReasonOk("  ok ")).toBe(false);
  expect(rejectReasonOk("touches pricing")).toBe(true);
});
