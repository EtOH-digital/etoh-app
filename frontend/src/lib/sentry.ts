/**
 * Sentry initialisation for the EtOH Expo app.
 *
 * Reads `EXPO_PUBLIC_SENTRY_DSN` from .env. When absent, every helper is a no-op,
 * so the app stays usable in dev or in tests.
 *
 * @sentry/react-native v7 transparently handles web + native through @sentry/react,
 * so a single import works for the Expo web preview, iOS and Android builds.
 */

import * as Sentry from "@sentry/react-native";

const DSN = process.env.EXPO_PUBLIC_SENTRY_DSN || "";
const ENV = process.env.EXPO_PUBLIC_SENTRY_ENVIRONMENT || "development";

let _initialized = false;

export function initSentry() {
  if (_initialized) return;
  if (!DSN) {
    // No DSN configured → keep Sentry disabled (no-op).
    return;
  }
  try {
    Sentry.init({
      dsn: DSN,
      environment: ENV,
      enableAutoSessionTracking: true,
      sendDefaultPii: false,
      tracesSampleRate: 0.1,
      // Drop common noisy errors (canceled requests, network blips on web preview)
      beforeSend(event, hint) {
        const exc: any = hint?.originalException;
        const msg = (exc && (exc.message || String(exc))) || "";
        if (typeof msg === "string") {
          if (msg.includes("AbortError") || msg.includes("Network request failed")) {
            return null;
          }
        }
        return event;
      },
    });
    _initialized = true;
    // eslint-disable-next-line no-console
    console.log("[Sentry] initialised", { env: ENV });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[Sentry] init failed", e);
  }
}

export function captureException(err: unknown, context?: Record<string, any>) {
  if (!_initialized || !DSN) {
    // eslint-disable-next-line no-console
    console.warn("[Sentry skipped]", err, context);
    return;
  }
  try {
    Sentry.captureException(err, { extra: context });
  } catch {}
}

export function setUser(user: { id: string; email?: string | null } | null) {
  if (!_initialized || !DSN) return;
  try {
    if (user) {
      Sentry.setUser({ id: user.id, email: user.email || undefined });
    } else {
      Sentry.setUser(null);
    }
  } catch {}
}

export { Sentry };
