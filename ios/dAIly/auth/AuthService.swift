import AuthenticationServices
import Foundation
import UIKit

// MARK: - Public Types

public enum AuthError: Error, Equatable {
    case unauthorized
    case server(Int)
    case decoding
    case network(String)
}

public struct PairingResult: Equatable {
    public let accessToken: String
    public let refreshToken: String
    public let expiresAt: Date
}

// MARK: - AuthService

@MainActor
public final class AuthService {
    private let baseURL: URL
    private let session: URLSession
    private let keychain: KeychainStore

    public init(baseURL: URL,
                session: URLSession = .shared,
                keychain: KeychainStore = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.keychain = keychain
    }

    /// Send a magic-link email to the given address.
    /// Returns void on success (backend always responds 204).
    public func sendLink(email: String) async throws {
        try await postJSON(path: "/auth/pair/send-link",
                           body: ["email": email],
                           expecting: EmptyResponse.self)
    }

    /// Exchange a pair code for access + refresh tokens.
    /// Persists all three Keychain entries on success.
    public func completePairing(code: String) async throws -> PairingResult {
        struct Resp: Decodable {
            let access_token: String
            let refresh_token: String
            let expires_in: Int
        }
        let r: Resp = try await postJSON(path: "/auth/pair/complete",
                                          body: ["code": code],
                                          expecting: Resp.self)
        let expires = Date().addingTimeInterval(TimeInterval(r.expires_in))
        try keychain.save(key: "access_token", value: r.access_token)
        try keychain.save(key: "refresh_token", value: r.refresh_token)
        try keychain.save(key: "access_token_expires_at",
                          value: ISO8601DateFormatter().string(from: expires))
        return PairingResult(accessToken: r.access_token,
                             refreshToken: r.refresh_token,
                             expiresAt: expires)
    }

    /// Refresh the access token using the stored refresh token.
    /// Persists the new access token and updated expiry to Keychain.
    public func refresh() async throws {
        guard let rt = keychain.load(key: "refresh_token") else {
            throw AuthError.unauthorized
        }
        struct Resp: Decodable {
            let access_token: String
            let expires_in: Int
        }
        let r: Resp = try await postJSON(path: "/auth/token/refresh",
                                          body: ["refresh_token": rt],
                                          expecting: Resp.self)
        let expires = Date().addingTimeInterval(TimeInterval(r.expires_in))
        try keychain.save(key: "access_token", value: r.access_token)
        try keychain.save(key: "access_token_expires_at",
                          value: ISO8601DateFormatter().string(from: expires))
    }

    // MARK: - Public integration methods

    /// Fetches the OAuth authorization URL for the given provider (D-13).
    /// Calls GET /integrations/{provider}/connect with Bearer access_token.
    /// Backend response shape is { "auth_url": "https://..." } — verified
    /// 21.1-RESEARCH.md §Confirmed API Contracts (the field name is auth_url,
    /// NOT authorization_url despite some earlier UI-SPEC drafts).
    public func getIntegrationConnectURL(provider: String) async throws -> URL {
        struct Resp: Decodable { let auth_url: String }
        let r: Resp = try await getJSON(
            path: "/integrations/\(provider)/connect",
            expecting: Resp.self
        )
        guard let url = URL(string: r.auth_url) else {
            throw AuthError.decoding
        }
        return url
    }

    /// Saves the user's briefing time and timezone preferences (D-15, D-16).
    /// Calls PUT /users/me/preferences (NOTE: /users/me/preferences, not
    /// /users/preferences — verified backend at src/daily/users/router.py:97).
    /// Returns on 204 No Content.
    public func savePreferences(briefingTime: String, timezone: String) async throws {
        try await putJSON(
            path: "/users/me/preferences",
            body: ["briefing_time": briefingTime, "timezone": timezone],
            expecting: EmptyResponse.self
        )
    }

    // MARK: - OAuth session

    // Held to keep the session and presentation provider alive for the duration
    // of the OAuth flow. Replaced on each new session start.
    private var currentOAuthSession: ASWebAuthenticationSession?
    private let oauthPresentationProvider = OAuthPresentationContextProvider()

    /// Opens an ASWebAuthenticationSession for the given OAuth authorization URL (D-13).
    ///
    /// Uses callbackURLScheme: nil because the OAuth callback is delivered as a
    /// Universal Link to /oauth/success?provider= — the system dismisses the
    /// session automatically and dAIlyApp.onOpenURL receives the redirect (see
    /// 21.1-RESEARCH.md §Pattern 3 and §Pitfall 4: do NOT use
    /// withCheckedThrowingContinuation here — the callback handler does not fire
    /// for Universal Link callbacks, and the continuation would never resume).
    ///
    /// Fire-and-forget: returns once the session has started. The caller updates
    /// UI reactively when IntegrationState.markConnected is called from
    /// dAIlyApp.onOpenURL.
    @MainActor
    public func openOAuthSession(url: URL) throws {
        let session = ASWebAuthenticationSession(
            url: url,
            callbackURLScheme: nil
        ) { _, _ in
            // Universal Link callbacks do not fire this handler. This closure is
            // intentionally a no-op; the only path that runs it is user
            // cancellation, in which case we simply tear down state.
        }
        session.presentationContextProvider = oauthPresentationProvider
        session.prefersEphemeralWebBrowserSession = false
        guard session.start() else {
            throw AuthError.network("ASWebAuthenticationSession failed to start")
        }
        self.currentOAuthSession = session
    }

    // MARK: - Private helpers

    private struct EmptyResponse: Decodable {}

    @discardableResult
    private func getJSON<T: Decodable>(path: String, expecting: T.Type) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "GET"
        if let token = keychain.load(key: "access_token") {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return try await sendAndDecode(req: req, expecting: expecting)
    }

    @discardableResult
    private func putJSON<T: Decodable>(path: String,
                                        body: [String: String],
                                        expecting: T.Type) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = keychain.load(key: "access_token") {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await sendAndDecode(req: req, expecting: expecting)
    }

    private func sendAndDecode<T: Decodable>(req: URLRequest, expecting: T.Type) async throws -> T {
        do {
            let (data, response) = try await session.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                throw AuthError.network("not an HTTP response")
            }
            if http.statusCode == 401 { throw AuthError.unauthorized }
            guard (200..<300).contains(http.statusCode) else {
                throw AuthError.server(http.statusCode)
            }
            if T.self == EmptyResponse.self {
                return EmptyResponse() as! T  // swiftlint:disable:this force_cast
            }
            do {
                return try JSONDecoder().decode(T.self, from: data)
            } catch {
                throw AuthError.decoding
            }
        } catch let e as AuthError {
            throw e
        } catch {
            throw AuthError.network(String(describing: error))
        }
    }

    @discardableResult
    private func postJSON<T: Decodable>(path: String,
                                         body: [String: String],
                                         expecting: T.Type) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await sendAndDecode(req: req, expecting: expecting)
    }
}

// MARK: - OAuthPresentationContextProvider

/// Provides the active foreground UIWindow for ASWebAuthenticationSession.
/// Required because the project uses pure SwiftUI lifecycle (@main struct App)
/// without a SceneDelegate.
@MainActor
final class OAuthPresentationContextProvider: NSObject, ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first(where: { $0.activationState == .foregroundActive })
            ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        return scene?.keyWindow
            ?? scene?.windows.first
            ?? UIWindow()
    }
}
