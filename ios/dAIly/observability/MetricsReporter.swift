import Foundation
import MetricKit
import os

/// Subscribes to MetricKit for crash and hang diagnostics.
///
/// This is the native Apple alternative to a hosted crash reporter
/// (Sentry/Crashlytics were deliberately not added here — this project does
/// not add new SPM dependencies without explicit approval). MetricKit is
/// built into iOS, requires no dependency, and delivers crash, hang, and CPU/
/// disk exception diagnostics directly from the OS roughly once a day.
///
/// This only logs payload summaries via os.Logger so they are visible in
/// device logs / sysdiagnose during development and TestFlight review.
/// Aggregating these across the full user base still requires a hosted
/// service (e.g. Sentry) — a separate dependency decision that needs
/// explicit approval before it's added.
final class MetricsReporter: NSObject, MXMetricManagerSubscriber {
    // Safe to share across isolation domains: this type is stateless (holds
    // only a static Logger) and MXMetricManager itself calls subscribers from
    // an arbitrary background queue, not necessarily MainActor.
    nonisolated(unsafe) static let shared = MetricsReporter()

    private static let logger = Logger(subsystem: "com.jacobmarriott.daily", category: "metrickit")

    private override init() {
        super.init()
    }

    /// Registers this instance with MXMetricManager. Call once at app launch.
    func start() {
        MXMetricManager.shared.add(self)
    }

    // MARK: - MXMetricManagerSubscriber

    func didReceive(_ payloads: [MXMetricPayload]) {
        Self.logger.info("MetricKit received \(payloads.count, privacy: .public) metric payload(s)")
    }

    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        for payload in payloads {
            let crashCount = payload.crashDiagnostics?.count ?? 0
            let hangCount = payload.hangDiagnostics?.count ?? 0
            let cpuExceptionCount = payload.cpuExceptionDiagnostics?.count ?? 0
            let diskWriteExceptionCount = payload.diskWriteExceptionDiagnostics?.count ?? 0

            if crashCount > 0 {
                Self.logger.fault("MetricKit crash diagnostic received: \(crashCount, privacy: .public) crash(es)")
            }
            if hangCount > 0 {
                Self.logger.error("MetricKit hang diagnostic received: \(hangCount, privacy: .public) hang(s)")
            }
            if cpuExceptionCount > 0 {
                Self.logger.error("MetricKit CPU exception diagnostic received: \(cpuExceptionCount, privacy: .public)")
            }
            if diskWriteExceptionCount > 0 {
                Self.logger.error("MetricKit disk write exception diagnostic received: \(diskWriteExceptionCount, privacy: .public)")
            }
        }
    }
}
