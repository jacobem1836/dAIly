import Foundation

/// Onboarding integration provider metadata (D-09, D-10).
/// Raw values match the backend `/integrations/{provider}/connect` path segment
/// exactly: google, microsoft, slack. Note: backend stores Microsoft as
/// provider="outlook" in the DB but the API path uses "microsoft" (verified in
/// 21.1-RESEARCH.md §Confirmed API Contracts).
public enum IntegrationProvider: String, CaseIterable, Sendable {
    case google     = "google"
    case microsoft  = "microsoft"
    case slack      = "slack"

    public var displayName: String {
        switch self {
        case .google:    return "Google"
        case .microsoft: return "Microsoft"
        case .slack:     return "Slack"
        }
    }

    public var description: String {
        switch self {
        case .google:
            return "Access Gmail and Google Calendar to include emails and events in your briefing."
        case .microsoft:
            return "Access Outlook and Microsoft Teams to include emails and meeting summaries."
        case .slack:
            return "Access your Slack channels and DMs for message highlights."
        }
    }

    public var icon: String {
        switch self {
        case .google:    return "envelope.circle.fill"
        case .microsoft: return "calendar.circle.fill"
        case .slack:     return "bubble.left.and.bubble.right.fill"
        }
    }
}
