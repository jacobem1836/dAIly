import Foundation

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

    // MARK: - Private helpers

    private struct EmptyResponse: Decodable {}

    @discardableResult
    private func postJSON<T: Decodable>(path: String,
                                         body: [String: String],
                                         expecting: T.Type) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

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
}
