import Foundation

public enum PairCodeURLParser {
    /// Extracts the pair code from a Universal Link URL.
    /// Returns nil unless the path is exactly "/pair" and the "code" query parameter is present.
    public static func extractPairCode(from url: URL) -> String? {
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              comps.path == "/pair" else { return nil }
        return comps.queryItems?.first(where: { $0.name == "code" })?.value
    }
}
