import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  init: vi.fn(), capture: vi.fn(), opt_in_capturing: vi.fn(), opt_out_capturing: vi.fn(), reset: vi.fn(),
}));
vi.mock("posthog-js", () => ({default:sdk}));

import { analyticsConsent, configureAnalytics, setAnalyticsConsent, track, trackCompletion, trackError } from "./analytics";

beforeEach(() => {localStorage.clear(); vi.clearAllMocks();});

describe("optional analytics", () => {
  it("honors a browser privacy signal even if opt-in is requested", async () => {
    Object.defineProperty(navigator,"globalPrivacyControl",{configurable:true,value:true});
    try {
      configureAnalytics({token:"public-test-token",host:"https://us.i.posthog.com"});
      setAnalyticsConsent(true);
      await track("page_view",{page:"home"});
      expect(analyticsConsent()).toBe("off");
      expect(sdk.capture).not.toHaveBeenCalled();
    } finally {delete (navigator as Navigator & {globalPrivacyControl?:boolean}).globalPrivacyControl;}
  });
  it("stays off by default, captures named events after opt-in, and stops after opt-out", async () => {
    configureAnalytics({token:"public-test-token",host:"https://us.i.posthog.com"});
    expect(analyticsConsent()).toBeNull();
    await track("page_view",{page:"home"});
    expect(sdk.init).not.toHaveBeenCalled();
    setAnalyticsConsent(true);
    await track("battle_started",{mode:"Classic",opponent:"heuristic"});
    expect(sdk.init).toHaveBeenCalledTimes(1);
    expect(sdk.capture).toHaveBeenCalledWith("battle_started",{mode:"Classic",opponent:"heuristic",$geoip_disable:true});
    const options=sdk.init.mock.calls[0][1] as {before_send:(event:{event:string;properties:Record<string,string>})=>{properties:Record<string,string>}};
    expect(options.before_send({event:"page_view",properties:{token:"public",distinct_id:"temporary",page:"home",email:"private",$current_url:"https://example.com/secret"}}).properties)
      .toEqual({token:"public",distinct_id:"temporary",page:"home"});
    trackCompletion("private-session-key",{mode:"Classic",duration_seconds:12});
    trackCompletion("private-session-key",{mode:"Classic",duration_seconds:12});
    trackError("order","rejected");
    await vi.waitFor(() => expect(sdk.capture).toHaveBeenCalledTimes(3));
    expect(JSON.stringify(sdk.capture.mock.calls)).not.toContain("private-session-key");
    setAnalyticsConsent(false);
    await track("page_view",{page:"play"});
    expect(sdk.capture).toHaveBeenCalledTimes(3);
    expect(sdk.opt_out_capturing).toHaveBeenCalledOnce();
  });
});
