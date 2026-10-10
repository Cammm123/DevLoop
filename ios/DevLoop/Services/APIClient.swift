import Foundation

enum APIError: LocalizedError, Equatable {
    case notConfigured, invalidURL, insecureURL, unauthorized, server(Int), invalidResponse, transport(String)
    var errorDescription: String? {
        switch self {
        case .notConfigured: "Enter both a private server URL and bearer token."
        case .invalidURL: "Enter a valid server URL without embedded credentials."
        case .insecureURL: "Use an HTTPS Tailscale URL."
        case .unauthorized: "The server rejected the bearer token."
        case .server(let code): "The server returned HTTP \(code)."
        case .invalidResponse: "The dashboard response could not be read."
        case .transport(let message): message
        }
    }
}

extension ServerCredentials {
    /// Produces the exact values that are tested and, on success, persisted.
    func normalizedForConnection() throws -> ServerCredentials {
        var normalizedURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        while normalizedURL.hasSuffix("/") { normalizedURL.removeLast() }
        let normalizedToken = token.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !normalizedURL.isEmpty, !normalizedToken.isEmpty else { throw APIError.notConfigured }
        guard let components = URLComponents(string: normalizedURL),
              components.host != nil,
              components.user == nil,
              components.password == nil else { throw APIError.invalidURL }
        guard components.scheme?.lowercased() == "https" else { throw APIError.insecureURL }
        return ServerCredentials(serverURL: normalizedURL, token: normalizedToken)
    }
}

protocol DashboardFetching {
    func fetchDashboard(credentials: ServerCredentials) async throws -> DashboardSnapshot
}

struct APIClient: DashboardFetching {
    var session: URLSession = .shared

    func fetchDashboard(credentials: ServerCredentials) async throws -> DashboardSnapshot {
        let credentials = try credentials.normalizedForConnection()
        guard var components = URLComponents(string: credentials.serverURL) else { throw APIError.invalidURL }
        let root = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + ([root, "v1/dashboard"].filter { !$0.isEmpty }).joined(separator: "/")
        components.queryItems = [URLQueryItem(name: "timezone", value: TimeZone.current.identifier)]
        components.fragment = nil
        guard let url = components.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.setValue("Bearer \(credentials.token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
            if http.statusCode == 401 || http.statusCode == 403 { throw APIError.unauthorized }
            guard (200..<300).contains(http.statusCode) else { throw APIError.server(http.statusCode) }
            if let dashboard = try? JSONDecoder.devLoop.decode(DashboardSnapshot.self, from: data) { return dashboard }
            if let aggregate = try? JSONDecoder.devLoop.decode(AggregateDashboard.self, from: data) { return aggregate.snapshot }
            throw APIError.invalidResponse
        } catch let error as APIError { throw error }
        catch { throw APIError.transport(error.localizedDescription) }
    }
}

/// Compatibility decoder for servers predating the rich DashboardSnapshot contract.
/// New servers decode directly above; this keeps upgrades non-breaking without
/// inventing distributions or achievement dates that the legacy payload lacks.
struct AggregateDashboard: Decodable {
    struct AggregateRing: Decodable { let value: Double; let goal: Double }
    struct Rings: Decodable { let time: AggregateRing; let output: AggregateRing; let consistency: AggregateRing }
    struct RecentEvent: Decodable {
        let occurredAt: Date; let source: String; let kind: String; let label: String?
        enum CodingKeys: String, CodingKey { case occurredAt = "occurred_at", source, kind, label }
    }
    let date: Date
    let rings: Rings
    let activeSeconds: Int
    let outputPoints: Double
    let activeDaysLast7: Int
    let eventCount: Int
    let xp: Int
    let streakDays: Int
    let recentEvents: [RecentEvent]
    enum CodingKeys: String, CodingKey {
        case date, rings, xp
        case activeSeconds = "active_seconds", outputPoints = "output_points"
        case activeDaysLast7 = "active_days_last_7", eventCount = "event_count"
        case streakDays = "streak_days", recentEvents = "recent_events"
    }

    var snapshot: DashboardSnapshot {
        let levelSize = 500
        let milestoneEvents = recentEvents.filter { $0.kind == "milestone" }.prefix(4)
        let achievements = milestoneEvents.enumerated().map { offset, item in
            Achievement(id: "\(item.occurredAt.timeIntervalSince1970)-\(offset)", title: item.label ?? "Milestone", detail: "Completed milestone", unlockedAt: item.occurredAt, symbol: "sparkles")
        }
        let activeMinutes = activeSeconds / 60
        let timeGoal = Int(rings.time.goal / 60)
        let outputGoal = rings.output.goal
        let consistencyGoal = rings.consistency.goal
        let summary = DailySummary(
            activeMinutes: activeMinutes,
            commits: recentEvents.filter { $0.kind == "commit" }.count,
            successfulChecks: 0,
            focusSessions: 0
        )
        return DashboardSnapshot(
            generatedAt: date,
            time: .init(kind: .time, value: rings.time.value / 60, goal: rings.time.goal / 60, unit: "min"),
            output: .init(kind: .output, value: rings.output.value, goal: outputGoal, unit: "pts"),
            consistency: .init(kind: .consistency, value: rings.consistency.value, goal: consistencyGoal, unit: "days"),
            xp: xp, level: max(1, xp / levelSize + 1), xpInLevel: xp % levelSize, xpForNextLevel: levelSize,
            streak: streakDays,
            goals: .init(activeMinutes: timeGoal, outputPoints: outputGoal, activeDays: Int(consistencyGoal), insight: "Goals adapt gradually from your recent active days."),
            trend: [.init(date: date, activeMinutes: Double(activeMinutes), outputPoints: outputPoints)],
            languages: [], projects: [], achievements: achievements,
            quests: [
                .init(id: "daily-focus", title: "Daily focus", current: Double(activeMinutes), target: Double(timeGoal), unit: "min"),
                .init(id: "daily-output", title: "Make progress", current: outputPoints, target: outputGoal, unit: "pts"),
                .init(id: "weekly-consistency", title: "Stay consistent", current: Double(activeDaysLast7), target: consistencyGoal, unit: "days")
            ],
            summary: summary
        )
    }
}
