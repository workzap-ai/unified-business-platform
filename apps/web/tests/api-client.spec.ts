import { expect, test } from "@playwright/test";
import {
  ApiError,
  apiRequest,
  bindApiWorkspace,
  errorMessage,
} from "../src/services/api-client";

test("file uploads preserve multipart boundaries, credentials and workspace guards", async () => {
  const original = globalThis.fetch;
  const form = new FormData();
  form.append("file", new Blob(["attachment content"]), "test.txt");
  form.append("request_id", "stable-request-id");
  bindApiWorkspace("tenant-a", "environment-b");
  let calls = 0;
  globalThis.fetch = async (_, options) => {
    calls++;
    expect(options?.body).toBe(form);
    expect(options?.credentials).toBe("include");
    const headers = new Headers(options?.headers);
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("X-Workspace-Tenant")).toBe("tenant-a");
    expect(headers.get("X-Workspace-Environment")).toBe("environment-b");
    return new Response(JSON.stringify({ status: "succeeded" }), {
      status: 201,
    });
  };
  try {
    await expect(
      apiRequest("POST", "/files/records/customer/123", null, { body: form }),
    ).resolves.toEqual({ status: "succeeded" });
    expect(calls).toBe(1);
  } finally {
    bindApiWorkspace(undefined, undefined);
    globalThis.fetch = original;
  }
});

test("network failures are classified without retrying a registration", async () => {
  const original = globalThis.fetch;
  let attempts = 0;
  globalThis.fetch = async () => {
    attempts++;
    throw new TypeError("Failed to fetch");
  };
  try {
    await expect(
      apiRequest("POST", "/auth/register", null, { body: {} }),
    ).rejects.toMatchObject({ code: "NETWORK_UNAVAILABLE", status: 0 });
    expect(attempts).toBe(1);
    expect(errorMessage(new ApiError(0, "NETWORK_UNAVAILABLE"))).toContain(
      "connect to the service",
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("proxy outages and backend errors have safe distinct messages", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response("Internal Server Error", { status: 500 });
  try {
    await expect(
      apiRequest("GET", "/auth/session", null),
    ).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE", status: 500 });
    expect(errorMessage(new ApiError(500, "SERVICE_UNAVAILABLE"))).toContain(
      "temporarily unavailable",
    );
    expect(
      errorMessage(
        new ApiError(
          500,
          "INTERNAL_ERROR",
          undefined,
          "secret database details",
        ),
      ),
    ).not.toContain("secret");
  } finally {
    globalThis.fetch = original;
  }
});
