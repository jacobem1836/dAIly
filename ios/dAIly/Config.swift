import Foundation

public enum Config {
    /// Single source of truth for the backend host.
    /// For local dev, set to your ngrok / Cloudflare Tunnel HTTPS URL.
    /// For production, set to your deployed FastAPI backend URL before TestFlight.
    ///
    /// Steps for local device testing:
    ///   1. Run: `cloudflared tunnel --url http://localhost:8000`
    ///   2. Paste the HTTPS URL (e.g. https://abcd-1234.trycloudflare.com) here
    ///   3. Update the `applinks:` entry in `ios/dAIly/dAIly.entitlements` to match the tunnel host
    ///   4. Re-run `xcodegen generate` if `project.yml` changed
    ///   5. Verify AASA: `curl https://<tunnel>/.well-known/apple-app-site-association`
    public static let backendBaseURL: URL = URL(string: "https://representative-yield-ala-tickets.trycloudflare.com")!
}
