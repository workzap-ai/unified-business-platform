"use client";

/**
 * Fingerprint lock (passkeys) for the pi app and pi Customer: Touch ID, Windows Hello,
 * an Android fingerprint or a security key, used only as the optional second step after
 * the password or WhatsApp code. The device does the fingerprint check; the server only
 * ever sees a signature from a key that never leaves the device.
 */

type Json = Record<string, unknown>;
type Post = <T>(path: string, body?: unknown) => Promise<T>;

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
  let binary = "";
  for (const b of new Uint8Array(value)) binary += String.fromCharCode(b);
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

/** What to call it on this device, for buttons and hints. */
export function unlockName(): string {
  if (typeof navigator === "undefined") return "fingerprint";
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad/.test(ua)) return "Face ID / Touch ID";
  if (ua.includes("macintosh")) return "Touch ID";
  if (ua.includes("windows")) return "Windows Hello";
  if (ua.includes("android")) return "fingerprint";
  return "fingerprint";
}

/** A friendly message, or null when the person simply cancelled. */
export function passkeyError(error: unknown): string | null {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "AbortError")
      return null;
    if (error.name === "InvalidStateError")
      return "This device already has a passkey for you.";
    if (error.name === "SecurityError")
      return "Passkeys need the secure pi address (https).";
  }
  return null;
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

export interface Passkey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  synced: boolean;
}

/** Has the device create a passkey (the Face ID prompt) and saves it. */
export async function addPasskey(
  post: Post,
  base: string,
  start: unknown,
  name: string,
): Promise<Passkey> {
  const o = await post<Json>(`${base}/register/options`, start);
  const user = o.user as Json;
  const credential = (await navigator.credentials.create({
    publicKey: {
      ...(o as unknown as PublicKeyCredentialCreationOptions),
      challenge: toBytes(String(o.challenge)),
      user: {
        id: toBytes(String(user.id)),
        name: String(user.name),
        displayName: String(user.displayName),
      },
      excludeCredentials: descriptors(o.excludeCredentials),
    },
  })) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
  const response = credential.response as AuthenticatorAttestationResponse;
  return post<Passkey>(`${base}/register/verify`, {
    name,
    credential: {
      id: credential.id,
      rawId: toText(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: toText(response.clientDataJSON),
        attestationObject: toText(response.attestationObject),
        transports: response.getTransports?.() ?? [],
      },
      clientExtensionResults: credential.getClientExtensionResults(),
    },
  });
}

/**
 * The optional fingerprint step after the password: the device signs a challenge for
 * this sign-in only (the ticket from the password step), with one of your passkeys.
 */
export async function fingerprintStep<T>(
  post: Post,
  base: string,
  ticket: string,
): Promise<T> {
  const started = await post<{ options: Json }>(
    `${base}/mfa/fingerprint/options`,
    { ticket },
  );
  const o = started.options;
  const credential = (await navigator.credentials.get({
    publicKey: {
      ...(o as unknown as PublicKeyCredentialRequestOptions),
      challenge: toBytes(String(o.challenge)),
      allowCredentials: descriptors(o.allowCredentials),
    },
  })) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
  const response = credential.response as AuthenticatorAssertionResponse;
  return post<T>(`${base}/mfa/fingerprint`, {
    ticket,
    credential: {
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
    },
  });
}
