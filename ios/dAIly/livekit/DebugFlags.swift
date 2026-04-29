import Foundation

/// Compile-time debug feature flags.
/// All flags are `false` (and `let`) in Release builds.
/// In DEBUG builds they are `var` and can be toggled at runtime in a debugger.
public enum DebugFlags {
    #if DEBUG
    /// Enable push-to-talk mode (D-07). When true, VoiceSession.setMicrophone(enabled:)
    /// is active. NEVER surfaced in production UI — debug/testing only.
    public static var pttEnabled: Bool = false
    #else
    public static let pttEnabled: Bool = false
    #endif
}
