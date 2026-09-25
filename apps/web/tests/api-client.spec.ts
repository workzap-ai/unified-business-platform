import { expect, test } from "@playwright/test";
import { ApiError, apiRequest, errorMessage } from "../src/services/api-client";

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
