import Foundation

enum DashboardFixture {
    static let snapshot: DashboardSnapshot = {
        let calendar = Calendar(identifier: .gregorian)
        let now = Date()
        let trend = (0..<14).map { offset in
            TrendPoint(date: calendar.date(byAdding: .day, value: offset - 13, to: now)!, activeMinutes: [38, 62, 54, 0, 73, 81, 46][offset % 7], outputPoints: [4, 8, 6, 0, 10, 12, 7][offset % 7])
        }
        return DashboardSnapshot(
            generatedAt: now,
            time: RingMetric(kind: .time, value: 52, goal: 65, unit: "min"),
            output: RingMetric(kind: .output, value: 8.4, goal: 10, unit: "pts"),
            consistency: RingMetric(kind: .consistency, value: 5, goal: 6, unit: "days"),
            xp: 4280, level: 12, xpInLevel: 280, xpForNextLevel: 500, streak: 9,
            goals: AdaptiveGoals(activeMinutes: 65, outputPoints: 10, activeDays: 6, insight: "A steady target based on your last 28 active days."),
            trend: trend,
            languages: [.init(name: "Swift", value: 46), .init(name: "Python", value: 31), .init(name: "TypeScript", value: 17), .init(name: "Other", value: 6)],
            projects: [.init(name: "DevLoop", value: 53), .init(name: "Atlas", value: 27), .init(name: "Dotfiles", value: 20)],
            achievements: [.init(id: "nine", title: "Momentum", detail: "9-day meaningful streak", unlockedAt: now, symbol: "flame.fill"), .init(id: "ship", title: "Ship Shape", detail: "10 successful builds", unlockedAt: now.addingTimeInterval(-86400), symbol: "shippingbox.fill")],
            quests: [.init(id: "focus", title: "Deep work", current: 2, target: 3, unit: "sessions"), .init(id: "checks", title: "Green checks", current: 4, target: 5, unit: "checks")],
            summary: .init(activeMinutes: 52, commits: 3, successfulChecks: 4, focusSessions: 2)
        )
    }()
}
