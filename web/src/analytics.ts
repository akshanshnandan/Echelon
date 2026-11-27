type EventName = "page_view" | "play_opened" | "battle_started" | "battle_completed" | "replay_downloaded" | "app_error";
type Properties = Record<string, string | number | boolean>;
type Client = typeof import("posthog-js").default;

let config: {token:string;host:string} | null = null;
let client: Client | null = null;
let loading: Promise<Client | null> | null = null;
const completed = new Set<string>();

export function analyticsConsent(): "on" | "off" | null {
  if (analyticsBlocked()) return "off";
  const choice = localStorage.getItem("echelon-analytics");
  return choice === "on" || choice === "off" ? choice : null;
}

export function analyticsBlocked() {
  const signal = navigator as Navigator & {globalPrivacyControl?: boolean};
  return !!signal.globalPrivacyControl || navigator.doNotTrack === "1";
}

export function configureAnalytics(next: {token:string;host:string}) {
  config = next.token && /^https:\/\//.test(next.host) ? next : null;
  if (analyticsConsent() === "on") void loadClient();
}

async function loadClient(): Promise<Client | null> {
  if (!config || analyticsConsent() !== "on") return null;
  if (client) return client;
  if (!loading) loading = import("posthog-js").then(({default: posthog}) => {
    if (!config || analyticsConsent() !== "on") return null;
    posthog.init(config.token, {
      api_host: config.host,
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      disable_session_recording: true,
      disable_surveys: true,
      advanced_disable_flags: true,
      request_batching: false,
      opt_out_useragent_filter: location.hostname === "127.0.0.1" || location.hostname === "localhost",
      person_profiles: "never",
      persistence: "memory",
      opt_out_capturing_by_default: true,
      before_send: (event) => {
        if (!event) return null;
        const allowed = ["token", "distinct_id", "page", "mode", "map", "opponent", "duration_seconds", "winner", "source", "kind", "$geoip_disable", "$process_person_profile"];
        event.properties = Object.fromEntries(Object.entries(event.properties ?? {}).filter(([key]) => allowed.includes(key)));
        return event;
      },
    });
    posthog.opt_in_capturing({captureEventName:false});
    client = posthog;
    return client;
  }).catch(() => null).finally(() => {loading = null;});
  return loading;
}

export function setAnalyticsConsent(enabled: boolean) {
  if (enabled && analyticsBlocked()) return;
  localStorage.setItem("echelon-analytics", enabled ? "on" : "off");
  if (enabled) {
    if (client) client.opt_in_capturing({captureEventName:false});
    else void loadClient();
  } else { client?.opt_out_capturing(); client?.reset(); }
}

export async function track(event: EventName, properties: Properties = {}) {
  const instance = await loadClient();
  if (analyticsConsent() !== "on") return;
  instance?.capture(event, {...properties, $geoip_disable:true});
}

export function trackCompletion(key: string, properties: Properties) {
  if (completed.has(key)) return;
  completed.add(key);
  void track("battle_completed", properties);
}

export function trackError(source: "setup" | "order" | "poll" | "control" | "replay" | "feedback", kind: "network" | "expired" | "rejected") {
  void track("app_error", {source,kind});
}
