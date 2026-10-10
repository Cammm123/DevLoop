import Combine
import Foundation
import OSLog
import WidgetKit

@MainActor
final class DashboardStore: ObservableObject {
    enum Phase: Equatable { case loading, loaded, empty, offline(String), needsSetup }
    @Published private(set) var snapshot: DashboardSnapshot?
    @Published private(set) var phase: Phase = .loading
    @Published private(set) var isRefreshing = false
    @Published private(set) var lastUpdated: Date?
    @Published private(set) var cacheWarning: String?

    private let api: any DashboardFetching
    private let cache: DashboardCache
    private let credentials: any CredentialStoring
    private let logger = Logger(subsystem: Bundle.main.bundleIdentifier ?? "DevLoop", category: "DashboardCache")

    init(api: any DashboardFetching = APIClient(), cache: DashboardCache = DashboardCache(), credentials: any CredentialStoring = CredentialStore.shared, preview: DashboardSnapshot? = nil) {
        self.api = api; self.cache = cache; self.credentials = credentials
        if let preview {
            snapshot = preview
            lastUpdated = Date()
            phase = .loaded
        }
    }

    func start() async {
        do {
            if let cached = try cache.load() {
                snapshot = cached.dashboard; lastUpdated = cached.savedAt; phase = .loaded
            }
        } catch {
            reportCacheFailure(error)
        }
        await refresh(showLoading: snapshot == nil)
    }

    func refresh(showLoading: Bool = false) async {
        if isRefreshing { return }
        isRefreshing = true; defer { isRefreshing = false }
        if showLoading { phase = .loading }
        let auth = credentials.load()
        guard !auth.serverURL.isEmpty, !auth.token.isEmpty else { phase = snapshot == nil ? .needsSetup : .loaded; return }
        do {
            let value = try await api.fetchDashboard(credentials: auth)
            apply(value)
            persistForWidget(value)
        } catch {
            phase = .offline(error.localizedDescription)
        }
    }

    /// Tests candidate credentials before changing Keychain. Existing working
    /// credentials remain untouched when validation or the dashboard request fails.
    @discardableResult
    func connect(using candidate: ServerCredentials) async throws -> ServerCredentials {
        let normalized = try candidate.normalizedForConnection()
        let value = try await api.fetchDashboard(credentials: normalized)
        try credentials.save(normalized)
        apply(value)
        persistForWidget(value)
        return normalized
    }

    private func apply(_ value: DashboardSnapshot) {
        snapshot = value
        lastUpdated = Date()
        phase = value.trend.isEmpty && value.achievements.isEmpty && value.rings.allSatisfy { $0.value == 0 } ? .empty : .loaded
    }

    private func persistForWidget(_ value: DashboardSnapshot) {
        do {
            try cache.save(value)
            cacheWarning = nil
            WidgetCenter.shared.reloadAllTimelines()
        } catch {
            reportCacheFailure(error)
        }
    }

    private func reportCacheFailure(_ error: Error) {
        let message = (error as? LocalizedError)?.errorDescription ?? "The dashboard could not be shared with the widget."
        cacheWarning = message
        logger.error("Dashboard cache unavailable: \(message, privacy: .public)")
    }
}
