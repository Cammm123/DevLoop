import Foundation

enum DashboardCacheError: LocalizedError, Equatable {
    case appGroupUnavailable(String)

    var errorDescription: String? {
        switch self {
        case .appGroupUnavailable:
            return "The shared App Group is unavailable. Check the signing and App Group configuration for the app and widget."
        }
    }
}

struct CachedDashboard: Codable, Equatable {
    let savedAt: Date
    let dashboard: DashboardSnapshot
}

struct DashboardCache {
    static let appGroup = "group.com.cameronkani.devloop"
    static let filename = "dashboard-cache.json"
    private let directoryProvider: () -> URL?

    /// Production cache. Failure to resolve the App Group is surfaced instead
    /// of writing data that the widget can never see to an app-private cache.
    init(fileManager: FileManager = .default) {
        directoryProvider = {
            fileManager.containerURL(forSecurityApplicationGroupIdentifier: Self.appGroup)
        }
    }

    /// Explicit directory injection for tests and previews, where App Group
    /// entitlements are not available.
    init(directory: URL) {
        directoryProvider = { directory }
    }

    /// Injectable resolver makes the missing-entitlement path deterministic in tests.
    init(directoryProvider: @escaping () -> URL?) {
        self.directoryProvider = directoryProvider
    }

    private func directory() throws -> URL {
        guard let directory = directoryProvider() else {
            throw DashboardCacheError.appGroupUnavailable(Self.appGroup)
        }
        return directory
    }

    func save(_ dashboard: DashboardSnapshot, now: Date = Date()) throws {
        let directory = try directory()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try JSONEncoder.devLoop.encode(CachedDashboard(savedAt: now, dashboard: dashboard))
        try data.write(to: directory.appendingPathComponent(Self.filename), options: .atomic)
    }

    func load() throws -> CachedDashboard? {
        let directory = try directory()
        let url = directory.appendingPathComponent(Self.filename)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return try JSONDecoder.devLoop.decode(CachedDashboard.self, from: Data(contentsOf: url))
    }

    func clear() throws {
        let directory = try directory()
        let url = directory.appendingPathComponent(Self.filename)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
}
