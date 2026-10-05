"use client";

/**
 * Passkeys in the browser: Face ID, Touch ID, Windows Hello, an Android fingerprint
 * or a security key. The browser and the device do the face/fingerprint check; the
 * server only ever sees a signature from a key that never leaves the device.
 */
import { apiRequest } from "@/services/api-client";

type Json = Record<string, unknown>;

function toBytes(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toText(value: ArrayBuffer | null | undefined): string | undefined {
  if (!value) return undefined;
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** True when this browser can use passkeys at all. */
export function passkeysAvailable(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof window.PublicKeyCredential === "function" &&
    Boolean(navigator.credentials)
  );
}

/** True when this device has a built-in unlock (Face ID, Touch ID, Windows Hello, fingerprint). */
export async function deviceUnlockAvailable(): Promise<boolean> {
  if (!passkeysAvailable()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** What to call it on this device, for buttons and hints. */
export function unlockName(): string {
  if (typeof navigator === "undefined") return "Face ID or fingerprint";
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad/.test(ua)) return "Face ID";
  if (ua.includes("macintosh")) return "Touch ID";
  if (ua.includes("windows")) return "Windows Hello";
  if (ua.includes("android")) return "fingerprint or face unlock";
  return "Face ID or fingerprint";
}

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] {
  return Array.isArray(list)
    ? list.map((d: Json) => ({
        type: "public-key" as const,
        id: toBytes(String(d.id)),
        transports: d.transports as AuthenticatorTransport[] | undefined,
      }))
    : [];
}

function creationOptions(o: Json): PublicKeyCredentialCreationOptions {
  const user = o.user as Json;
  return {
    ...(o as unknown as PublicKeyCredentialCreationOptions),
    challenge: toBytes(String(o.challenge)),
    user: {
      id: toBytes(String(user.id)),
      name: String(user.name),
      displayName: String(user.displayName),
    },
    excludeCredentials: descriptors(o.excludeCredentials),
  };
}

function requestOptions(o: Json): PublicKeyCredentialRequestOptions {
  return {
    ...(o as unknown as PublicKeyCredentialRequestOptions),
    challenge: toBytes(String(o.challenge)),
    allowCredentials: descriptors(o.allowCredentials),
  };
}

function registrationJson(credential: PublicKeyCredential): Json {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toText(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toText(response.clientDataJSON),
      attestationObject: toText(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
  };
}

function assertionJson(credential: PublicKeyCredential): Json {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toText(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toText(response.clientDataJSON),
      authenticatorData: toText(response.authenticatorData),
      signature: toText(response.signature),
      userHandle: toText(response.userHandle),
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
  };
}

/** A friendly message for the errors people actually hit. */
export function passkeyError(error: unknown): string | null {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "AbortError")
      return null; // they cancelled, or it timed out: nothing to report
    if (error.name === "InvalidStateError")
      return "This device already has a passkey for your account.";
    if (error.name === "SecurityError")
      return "Passkeys need the secure Owner OS address (https).";
  }
  return "Couldn't use the passkey. Please try again.";
}

export interface Passkey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  synced: boolean;
}

export const passkeyApi = {
  list: () => apiRequest<Passkey[]>("GET", "/auth/passkeys", null),
  rename: (id: string, name: string) =>
    apiRequest<Passkey>("PATCH", `/auth/passkeys/${id}`, null, {
      body: { name },
    }),
  remove: (id: string) => apiRequest("DELETE", `/auth/passkeys/${id}`, null),
  /** Asks for the password, then has the device create the passkey (Face ID prompt). */
  async add(password: string, name: string): Promise<Passkey> {
    const options = await apiRequest<Json>(
      "POST",
      "/auth/passkeys/register/options",
      null,
      { body: { password } },
    );
    const credential = (await navigator.credentials.create({
      publicKey: creationOptions(options),
    })) as PublicKeyCredential | null;
    if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
    return apiRequest<Passkey>("POST", "/auth/passkeys/register/verify", null, {
      body: { credential: registrationJson(credential), name },
    });
  },
};

/** Runs the sign-in ceremony and returns the raw session payload from the API. */
export async function passkeySignIn<T>(
  verify: (body: { flow: string; credential: Json }) => Promise<T>,
): Promise<T> {
  const started = await apiRequest<{ flow: string; options: Json }>(
    "POST",
    "/auth/passkeys/login/options",
    null,
    { body: {} },
  );
  const credential = (await navigator.credentials.get({
    publicKey: requestOptions(started.options),
  })) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
  return verify({ flow: started.flow, credential: assertionJson(credential) });
}
