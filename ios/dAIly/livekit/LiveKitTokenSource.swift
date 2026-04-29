import Foundation

// MARK: - Types

public struct LiveKitToken: Equatable {
    public let token: String
    public let room: String
    public let url: String
}

public enum LiveKitTokenError: Error, Equatable {
    case unauthorized
    case server(Int)
    case decoding
    case network(String)
}

// MARK: - LiveKitTokenSource

/// Fetches a LiveKit room token from POST /livekit/token using Bearer JWT auth.
/// Backend (Phase 18) returns {token, room, livekit_url}.
public final class LiveKitTokenSource {
    private let baseURL: URL
    private let session: URLSession

    public init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    /// POST /livekit/token with Authorization: Bearer <accessJWT>
    /// Returns a LiveKitToken on success.
    /// Throws LiveKitTokenError.unauthorized on 401, .decoding on bad JSON, .server on other non-2xx.
    public func fetchToken(accessJWT: String) async throws -> LiveKitToken {
        var req = URLRequest(url: baseURL.appendingPathComponent("/livekit/token"))
        req.httpMethod = "POST"
        req.setValue("Bearer \(accessJWT)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data("{}".utf8)

        do {
            let (data, response) = try await session.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                throw LiveKitTokenError.network("not http")
            }
            if http.statusCode == 401 { throw LiveKitTokenError.unauthorized }
            guard (200..<300).contains(http.statusCode) else {
                throw LiveKitTokenError.server(http.statusCode)
            }
            struct Resp: Decodable {
                let token: String
                let room: String
                let livekit_url: String
            }
            let r = try JSONDecoder().decode(Resp.self, from: data)
            return LiveKitToken(token: r.token, room: r.room, url: r.livekit_url)
        } catch let e as LiveKitTokenError {
            throw e
        } catch is DecodingError {
            throw LiveKitTokenError.decoding
        } catch {
            throw LiveKitTokenError.network(String(describing: error))
        }
    }
}
