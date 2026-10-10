import Foundation
import Security

enum KeychainError: LocalizedError {
    case unexpectedStatus(OSStatus)
    var errorDescription: String? { "Keychain operation failed (\(statusDescription))." }
    private var statusDescription: String { if case .unexpectedStatus(let status) = self { return String(status) }; return "unknown" }
}

struct ServerCredentials: Equatable { var serverURL: String; var token: String }

protocol CredentialStoring: AnyObject {
    func load() -> ServerCredentials
    func save(_ credentials: ServerCredentials) throws
}

final class CredentialStore: CredentialStoring {
    static let shared = CredentialStore()
    private let service = "com.cameronkani.devloop.credentials"
    private enum Account { static let serverURL = "server-url"; static let token = "bearer-token" }

    func load() -> ServerCredentials {
        ServerCredentials(serverURL: (try? read(Account.serverURL)) ?? "", token: (try? read(Account.token)) ?? "")
    }

    func save(_ credentials: ServerCredentials) throws {
        try write(credentials.serverURL.trimmingCharacters(in: .whitespacesAndNewlines), account: Account.serverURL)
        try write(credentials.token.trimmingCharacters(in: .whitespacesAndNewlines), account: Account.token)
    }

    func clear() throws { try delete(Account.serverURL); try delete(Account.token) }

    private func read(_ account: String) throws -> String? {
        var query = baseQuery(account); query[kSecReturnData as String] = true; query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = item as? Data else { throw KeychainError.unexpectedStatus(status) }
        return String(data: data, encoding: .utf8)
    }

    private func write(_ value: String, account: String) throws {
        let data = Data(value.utf8); let query = baseQuery(account)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = query; add[kSecValueData as String] = data; add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let addStatus = SecItemAdd(add as CFDictionary, nil)
            guard addStatus == errSecSuccess else { throw KeychainError.unexpectedStatus(addStatus) }
        } else if status != errSecSuccess { throw KeychainError.unexpectedStatus(status) }
    }

    private func delete(_ account: String) throws {
        let status = SecItemDelete(baseQuery(account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError.unexpectedStatus(status) }
    }

    private func baseQuery(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
    }
}
