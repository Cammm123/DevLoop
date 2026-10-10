import Foundation

struct DashboardSnapshot: Codable, Equatable, Sendable {
    let generatedAt: Date
    let time: RingMetric
    let output: RingMetric
    let consistency: RingMetric
    let xp: Int
    let level: Int
    let xpInLevel: Int
    let xpForNextLevel: Int
    let streak: Int
    let goals: AdaptiveGoals
    let trend: [TrendPoint]
    let languages: [DistributionItem]
    let projects: [DistributionItem]
    let achievements: [Achievement]
    let quests: [Quest]
    let summary: DailySummary

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at", time, output, consistency, xp, level
        case xpInLevel = "xp_in_level", xpForNextLevel = "xp_for_next_level"
        case streak, goals, trend, languages, projects, achievements, quests, summary
    }

    var rings: [RingMetric] { [time, output, consistency] }
    var levelProgress: Double { Self.progress(value: Double(xpInLevel), goal: Double(xpForNextLevel)) }

    static func progress(value: Double, goal: Double) -> Double {
        guard value.isFinite, goal.isFinite, goal > 0 else { return 0 }
        return min(max(value / goal, 0), 1)
    }
}

struct RingMetric: Codable, Equatable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable { case time, output, consistency }
    let kind: Kind
    let value: Double
    let goal: Double
    let unit: String
    var id: Kind { kind }
    var progress: Double { DashboardSnapshot.progress(value: value, goal: goal) }
}

struct AdaptiveGoals: Codable, Equatable, Sendable {
    let activeMinutes: Int
    let outputPoints: Double
    let activeDays: Int
    let insight: String
    enum CodingKeys: String, CodingKey {
        case activeMinutes = "active_minutes", outputPoints = "output_points"
        case activeDays = "active_days", insight
    }
}

struct TrendPoint: Codable, Equatable, Identifiable, Sendable {
    let date: Date
    let activeMinutes: Double
    let outputPoints: Double
    var id: Date { date }
    enum CodingKeys: String, CodingKey { case date; case activeMinutes = "active_minutes"; case outputPoints = "output_points" }
}

struct DistributionItem: Codable, Equatable, Identifiable, Sendable {
    let name: String
    let value: Double
    var id: String { name }
}

struct Achievement: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let title: String
    let detail: String
    let unlockedAt: Date
    let symbol: String
    enum CodingKeys: String, CodingKey { case id, title, detail; case unlockedAt = "unlocked_at"; case symbol }
}

struct Quest: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let title: String
    let current: Double
    let target: Double
    let unit: String
    var progress: Double { DashboardSnapshot.progress(value: current, goal: target) }
}

struct DailySummary: Codable, Equatable, Sendable {
    let activeMinutes: Int
    let commits: Int
    let successfulChecks: Int
    let focusSessions: Int
    enum CodingKeys: String, CodingKey {
        case activeMinutes = "active_minutes", commits
        case successfulChecks = "successful_checks", focusSessions = "focus_sessions"
    }
}

extension JSONDecoder {
    static var devLoop: JSONDecoder {
        let decoder = JSONDecoder()
        let precise = ISO8601DateFormatter(); precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let ordinary = ISO8601DateFormatter(); ordinary.formatOptions = [.withInternetDateTime]
        let day = DateFormatter(); day.locale = Locale(identifier: "en_US_POSIX"); day.dateFormat = "yyyy-MM-dd"
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            if let seconds = try? container.decode(Double.self) {
                return Date(timeIntervalSince1970: seconds)
            }
            let value = try container.decode(String.self)
            if let date = precise.date(from: value) ?? ordinary.date(from: value) ?? day.date(from: value) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid date: \(value)")
        }
        return decoder
    }
}

extension JSONEncoder {
    static var devLoop: JSONEncoder {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        // Numeric timestamps preserve full Date precision in the private widget cache.
        encoder.dateEncodingStrategy = .secondsSince1970
        return encoder
    }
}
