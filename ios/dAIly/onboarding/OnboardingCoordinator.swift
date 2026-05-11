import Foundation
import Combine

// MARK: - OnboardingStep

/// Named steps in the onboarding flow.
/// Tab indices in OnboardingView correspond 1:1 with these cases.
enum OnboardingStep: Int, CaseIterable, Equatable {
    case welcome      = 0
    case pairing      = 1
    case google       = 2
    case microsoft    = 3
    case slack        = 4
    case permissions  = 5
    case schedule     = 6
    case completion   = 7

    /// Human-readable label (used in debug / test assertions).
    var label: String {
        switch self {
        case .welcome:     return "welcome"
        case .pairing:     return "pairing"
        case .google:      return "google"
        case .microsoft:   return "microsoft"
        case .slack:       return "slack"
        case .permissions: return "permissions"
        case .schedule:    return "schedule"
        case .completion:  return "completion"
        }
    }
}

// MARK: - OnboardingCoordinator

/// Testable model that owns the onboarding step machine.
///
/// OnboardingView drives its @State currentTab from this coordinator's
/// `currentStep` so the gate and advance logic can be unit-tested without
/// SwiftUI rendering.
final class OnboardingCoordinator: ObservableObject {
    @Published var currentStep: OnboardingStep = .welcome

    // Gate conditions — set by the owning view or tests
    var hasAccessToken: Bool = false
    var atLeastOneIntegrationConnected: Bool = false
    var micPermissionGranted: Bool = false
    var scheduleSaved: Bool = false

    // MARK: - Gate

    /// Highest step the user may currently reach.
    var maximumReachableStep: OnboardingStep {
        if !hasAccessToken { return .pairing }
        if !atLeastOneIntegrationConnected { return .slack }
        if !micPermissionGranted { return .permissions }
        if !scheduleSaved { return .schedule }
        return .completion
    }

    /// True when the current step can advance to the next one.
    var canAdvance: Bool {
        guard let next = nextStep else { return false }
        return next.rawValue <= maximumReachableStep.rawValue
    }

    // MARK: - Navigation

    /// Advance one step if the gate allows it.
    /// Returns true if the step changed.
    @discardableResult
    func advance() -> Bool {
        guard canAdvance, let next = nextStep else { return false }
        currentStep = next
        return true
    }

    /// Go back one step. Always allowed (no gate). No-op at .welcome.
    /// Returns true if the step changed.
    @discardableResult
    func back() -> Bool {
        guard let prev = previousStep else { return false }
        currentStep = prev
        return true
    }

    // MARK: - Helpers

    private var nextStep: OnboardingStep? {
        OnboardingStep(rawValue: currentStep.rawValue + 1)
    }

    private var previousStep: OnboardingStep? {
        guard currentStep.rawValue > 0 else { return nil }
        return OnboardingStep(rawValue: currentStep.rawValue - 1)
    }
}
