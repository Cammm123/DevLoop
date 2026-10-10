import XCTest
@testable import DevLoop

final class DashboardStoreTests: XCTestCase {
    @MainActor
    func testFailedCandidateDoesNotReplaceWorkingCredentials() async {
        let existing = ServerCredentials(serverURL: "https://working.example.test", token: "working-token")
        let credentials = MemoryCredentials(existing)
        let store = DashboardStore(
            api: StubDashboardAPI(result: .failure(APIError.unauthorized)),
            cache: temporaryCache(),
            credentials: credentials
        )

        do {
            _ = try await store.connect(using: .init(serverURL: "https://candidate.example.test", token: "bad-token"))
            XCTFail("Expected candidate connection to fail")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }

        XCTAssertEqual(credentials.load(), existing)
        XCTAssertEqual(credentials.saveCount, 0)
    }

    @MainActor
    func testSuccessfulCandidateIsNormalizedThenSaved() async throws {
        let credentials = MemoryCredentials(.init(serverURL: "https://working.example.test", token: "working-token"))
        let api = StubDashboardAPI(result: .success(DashboardFixture.snapshot))
        let store = DashboardStore(api: api, cache: temporaryCache(), credentials: credentials)

        let normalized = try await store.connect(using: .init(
            serverURL: "  https://candidate.example.test/base/// ",
            token: " candidate-token\n"
        ))

        XCTAssertEqual(normalized, .init(serverURL: "https://candidate.example.test/base", token: "candidate-token"))
        XCTAssertEqual(api.receivedCredentials, normalized)
        XCTAssertEqual(credentials.load(), normalized)
        XCTAssertEqual(credentials.saveCount, 1)
        XCTAssertEqual(store.snapshot, DashboardFixture.snapshot)
    }

    private func temporaryCache() -> DashboardCache {
        DashboardCache(directory: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true))
    }
}

private final class StubDashboardAPI: DashboardFetching {
    let result: Result<DashboardSnapshot, Error>
    private(set) var receivedCredentials: ServerCredentials?

    init(result: Result<DashboardSnapshot, Error>) {
        self.result = result
    }

    func fetchDashboard(credentials: ServerCredentials) async throws -> DashboardSnapshot {
        receivedCredentials = credentials
        return try result.get()
    }
}

private final class MemoryCredentials: CredentialStoring {
    private var value: ServerCredentials
    private(set) var saveCount = 0

    init(_ value: ServerCredentials) {
        self.value = value
    }

    func load() -> ServerCredentials { value }

    func save(_ credentials: ServerCredentials) throws {
        value = credentials
        saveCount += 1
    }
}
