import Foundation

/// Parses Universal Link callbacks from the OAuth success redirect.
///
/// The backend redirects to `/oauth/success?provider={google|microsoft|slack}`
/// after a successful OAuth flow (verified in src/daily/integrations/router.py
/// line 210 — see 21.1-RESEARCH.md §Confirmed API Contracts).
///
/// SEC-01 compliance: only a `provider` signal is carried — no token. The
/// parser intentionally does not validate the provider raw value against the
/// IntegrationProvider enum so that backend-side additions don't require a
/// client release; the caller (dAIlyApp.onOpenURL) is responsible for ignoring
/// unknown providers.
public enum OAuthCallbackParser {
    /// Returns the `provider` query parameter for paths ending in
    /// `/oauth/success`. Returns nil when path doesn't match, query is missing,
    /// or the value is empty.
    public static func extractProvider(from url: URL) -> String? {
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              comps.path.hasSuffix("/oauth/success") else { return nil }
        guard let value = comps.queryItems?.first(where: { $0.name == "provider" })?.value,
              !value.isEmpty else { return nil }
        return value
    }
}
