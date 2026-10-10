import XCTest
@testable import DevLoop

final class DashboardCacheTests: XCTestCase {
    func testCacheRoundTripAndClear() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let cache = DashboardCache(directory: folder)
        let timestamp = Date(timeIntervalSince1970: 1_700_000_000)
        try cache.save(DashboardFixture.snapshot, now: timestamp)
        let loaded = try XCTUnwrap(cache.load())
        XCTAssertEqual(loaded.savedAt.timeIntervalSince1970, timestamp.timeIntervalSince1970, accuracy: 1)
        XCTAssertEqual(loaded.dashboard, DashboardFixture.snapshot)
        try cache.clear()
        XCTAssertNil(try cache.load())
    }

    func testMissingAppGroupThrowsTypedErrorInsteadOfUsingPrivateCache() {
        let cache = DashboardCache(directoryProvider: { nil })

        XCTAssertThrowsError(try cache.load()) { error in
            XCTAssertEqual(error as? DashboardCacheError, .appGroupUnavailable(DashboardCache.appGroup))
        }
        XCTAssertThrowsError(try cache.save(DashboardFixture.snapshot)) { error in
            XCTAssertEqual(error as? DashboardCacheError, .appGroupUnavailable(DashboardCache.appGroup))
        }
    }
}