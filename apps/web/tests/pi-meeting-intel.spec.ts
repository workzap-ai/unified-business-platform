import { expect, test } from "@playwright/test";
import {
  approvalEffect,
  clock,
  insightSchema,
  isSwitchedOff,
  meetingIntelService,
} from "../src/features/pi/meeting-intel-service";
import { ApiError, bindApiWorkspace } from "../src/services/api-client";

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

const meeting = {
  id: "m1",
  title: "Kickoff call",
  customer_id: null,
  source: "upload",
  status: "review",
  language: "",
  consent_at: "2026-11-05T10:00:00Z",
  has_recording: false,
  duration_ms: 0,
  held_at: null,
  retention_until: null,
  failure_reason: "",
  created_at: "2026-11-05T10:00:00Z",
};

test("a meeting with its transcript and insights parses the API shape", async () => {
  await withFetch(
    () => ({
      body: {
        ...meeting,
        participants: ["Customer", "Staff"],
        segments: [
          {
            ordinal: 0,
            start_ms: 0,
            end_ms: 0,
            speaker: "Customer",
            text: "stock runs out",
          },
        ],
        insights: [
          {
            id: "i1",
            kind: "problem",
            basis: "stated",
            text: "stock runs out",
            confidence: 90,
            segment_refs: [0],
            owner_label: "",
            due_text: "",
            review_status: "pending",
            written_to_brain: false,
            brain_ref: "",
          },
        ],
      },
    }),
    async (calls) => {
      const detail = await meetingIntelService.get("m1");
      expect(calls[0].url).toContain("/pi/meeting-intel/m1");
      expect(detail.segments[0].speaker).toBe("Customer");
      expect(detail.insights[0].basis).toBe("stated");
    },
  );
});

test("an unknown kind or basis from the server degrades instead of breaking the page", () => {
  const parsed = insightSchema.parse({
    id: "i2",
    kind: "gossip",
    basis: "certain",
    text: "x",
  });
  // an unknown basis is shown as pi's own conclusion, never as something a person said
  expect(parsed.basis).toBe("inferred");
  expect(parsed.review_status).toBe("pending");
});

test("approving sends the reviewer's own wording and reports what was written", async () => {
  await withFetch(
    () => ({
      body: {
        id: "i1",
        kind: "problem",
        basis: "stated",
        text: "edited",
        review_status: "edited",
        written_to_brain: true,
        wrote: "problem",
      },
    }),
    async (calls) => {
      const r = await meetingIntelService.approve("m1", "i1", "edited");
      expect(calls[0].method).toBe("POST");
      expect(calls[0].url).toContain(
        "/pi/meeting-intel/m1/insights/i1/approve",
      );
      expect(calls[0].body).toEqual({ edited_text: "edited" });
      expect(r.wrote).toBe("problem");
    },
  );
});

test("the switched-off error is recognised so the page can explain it", async () => {
  await withFetch(
    () => ({
      status: 403,
      body: {
        error: { code: "MEETING_INTEL_OFF", message: "off", request_id: "r1" },
      },
    }),
    async () => {
      const error = await meetingIntelService.list().catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiError);
      expect(isSwitchedOff(error)).toBe(true);
    },
  );
  expect(isSwitchedOff(new Error("x"))).toBe(false);
});

test("what approving does is said truthfully, and a guess is never called a fact", () => {
  const base = insightSchema.parse({
    id: "i",
    kind: "problem",
    basis: "stated",
    text: "t",
  });
  expect(approvalEffect(base)).toContain("problem list");
  expect(approvalEffect({ ...base, kind: "decision" })).toContain("decision");
  expect(approvalEffect({ ...base, kind: "next_step" })).toContain("Requests");
  const guess = approvalEffect({ ...base, basis: "inferred", kind: "problem" });
  expect(guess).toContain("never saved as something the customer said");
  expect(
    approvalEffect({ ...base, basis: "estimate", kind: "action" }),
  ).toContain("never saved");
});

test("clock formats a position in a recording and hides an untimed import", () => {
  expect(clock(65_000)).toBe("1:05");
  expect(clock(0)).toBe("");
});
