import Foundation
import os

public enum Config {
    /// Backend host, injected per build configuration via Debug.xcconfig /
    /// Release.xcconfig (DAILY_BACKEND_BASE_URL → Info.plist
    /// DailyBackendBaseURL). Keeping this in xcconfig rather than hardcoded
    /// Swift source means Release always builds against the production
    /// backend and a local dev tunnel URL can never accidentally ship in a
    /// TestFlight/App Store build — only Debug.xcconfig is expected to be
    /// edited for local testing (see that file for the steps).
    public static let backendBaseURL: URL = {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: "DailyBackendBaseURL") as? String,
              !raw.isEmpty,
              !raw.hasPrefix("$("), // unresolved build-setting placeholder
              let url = URL(string: raw) else {
            // Should only happen if the xcconfig/Info.plist wiring is broken
            // (e.g. a non-xcodegen build). Fail safe to production rather
            // than crash — this literal is a compile-time-known-valid URL,
            // not user/environment input.
            Logger(subsystem: "com.jacobmarriott.daily", category: "config")
                .fault("DailyBackendBaseURL missing/invalid in Info.plist — check Debug.xcconfig/Release.xcconfig")
            return URL(string: "https://api.getdaily.dev")!
        }
        return url
    }()
}
