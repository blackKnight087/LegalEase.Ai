/**
 * Lightweight product analytics — PostHog when configured, no-op otherwise.
 */

type AnalyticsProps = Record<string, string | number | boolean | undefined>;

const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY?.trim() || "";
const POSTHOG_HOST =
  (process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com").replace(/\/$/, "");

let identifiedUserId: string | null = null;

function canTrack(): boolean {
  return typeof window !== "undefined" && Boolean(POSTHOG_KEY);
}

export function identifyUser(
  userId: string,
  props?: { username?: string; membership?: string; role?: string }
) {
  if (!canTrack()) return;
  identifiedUserId = userId;
  capture("$identify", {
    distinct_id: userId,
    ...props,
  });
}

export function resetAnalytics() {
  identifiedUserId = null;
}

export function trackEvent(name: string, props?: AnalyticsProps) {
  if (!canTrack()) return;
  capture(name, {
    distinct_id: identifiedUserId || undefined,
    ...props,
  });
}

function capture(event: string, properties: AnalyticsProps) {
  const body = {
    api_key: POSTHOG_KEY,
    event,
    properties: {
      ...properties,
      $lib: "legalease-web",
    },
    timestamp: new Date().toISOString(),
  };
  fetch(`${POSTHOG_HOST}/capture/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    keepalive: true,
  }).catch(() => {});
}

export const ProductEvents = {
  login: "user_login",
  logout: "user_logout",
  signup: "user_signup",
  chatMessage: "chat_message_sent",
  chatFeedback: "chat_feedback",
  documentUpload: "document_uploaded",
  matterCreated: "matter_created",
  planUpgrade: "plan_upgrade_clicked",
  pageView: "page_view",
} as const;
