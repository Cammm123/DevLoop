import XCTest
@testable import DevLoop

final class DashboardModelTests: XCTestCase {
    func testRingProgressClampsAndHandlesInvalidGoals() {
        XCTAssertEqual(RingMetric(kind: .time, value: 50, goal: 100, unit: "min").progress, 0.5)
        XCTAssertEqual(RingMetric(kind: .output, value: 120, goal: 100, unit: "pts").progress, 1)
        XCTAssertEqual(RingMetric(kind: .consistency, value: -2, goal: 5, unit: "days").progress, 0)
        XCTAssertEqual(RingMetric(kind: .time, value: 1, goal: 0, unit: "min").progress, 0)
    }

    func testDashboardDecoding() throws {
        let json = #"""
        {"generated_at":"2026-10-10T08:30:00Z","time":{"kind":"time","value":45,"goal":60,"unit":"min"},"output":{"kind":"output","value":6,"goal":8,"unit":"pts"},"consistency":{"kind":"consistency","value":4,"goal":5,"unit":"days"},"xp":1200,"level":4,"xp_in_level":200,"xp_for_next_level":400,"streak":3,"goals":{"active_minutes":60,"output_points":8,"active_days":5,"insight":"Keep it steady."},"trend":[{"date":"2026-10-10","active_minutes":45,"output_points":6}],"languages":[{"name":"Swift","value":100}],"projects":[],"achievements":[],"quests":[{"id":"q1","title":"Focus","current":1,"target":2,"unit":"sessions"}],"summary":{"active_minutes":45,"commits":2,"successful_checks":3,"focus_sessions":1}}
        """#.data(using: .utf8)!
        let value = try JSONDecoder.devLoop.decode(DashboardSnapshot.self, from: json)
        XCTAssertEqual(value.level, 4)
        XCTAssertEqual(value.time.progress, 0.75)
        XCTAssertEqual(value.trend.count, 1)
        XCTAssertEqual(value.languages.first?.name, "Swift")
    }

    func testCurrentServerAggregateAdaptsToLocalDashboard() throws {
        let json = #"""
        {"date":"2026-03-10","timezone":"UTC","rings":{"time":{"value":1800,"goal":3600,"progress":0.5},"output":{"value":4,"goal":20,"progress":0.2},"consistency":{"value":3,"goal":5,"progress":0.6}},"active_seconds":1800,"output_points":4,"active_days_last_7":3,"event_count":2,"xp":508,"streak_days":3,"recent_events":[]}
        """#.data(using: .utf8)!
        let aggregate = try JSONDecoder.devLoop.decode(AggregateDashboard.self, from: json)
        XCTAssertEqual(aggregate.snapshot.time.value, 30)
        XCTAssertEqual(aggregate.snapshot.level, 2)
        XCTAssertEqual(aggregate.snapshot.xpInLevel, 8)
        XCTAssertEqual(aggregate.snapshot.trend.count, 1)
        XCTAssertEqual(aggregate.snapshot.quests.map(\.id), ["daily-focus", "daily-output", "weekly-consistency"])
        XCTAssertEqual(aggregate.snapshot.summary.activeMinutes, 30)
    }

    func testCredentialsNormalizeBeforeConnection() throws {
        let value = try ServerCredentials(serverURL: "  https://devloop.example.test/base///  ", token: "  secret-token\n").normalizedForConnection()
        XCTAssertEqual(value.serverURL, "https://devloop.example.test/base")
        XCTAssertEqual(value.token, "secret-token")
    }

    func testCredentialsRejectInsecureAndEmptyValues() {
        XCTAssertThrowsError(try ServerCredentials(serverURL: "http://devloop.example.test", token: "token").normalizedForConnection()) {
            XCTAssertEqual($0 as? APIError, .insecureURL)
        }
        XCTAssertThrowsError(try ServerCredentials(serverURL: "https://devloop.example.test", token: "  ").normalizedForConnection()) {
            XCTAssertEqual($0 as? APIError, .notConfigured)
        }
    }
}