import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var dashboardStore: DashboardStore
    @State private var serverURL = ""
    @State private var token = ""
    @State private var status: Status?
    @State private var saving = false
    @FocusState private var focused: Field?
    private enum Field { case url, token }
    private enum Status { case success(String), failure(String) }

    var body: some View {
        Form {
            Section {
                TextField("https://devloop.your-tailnet.ts.net", text: $serverURL).textContentType(.URL).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled().focused($focused, equals: .url)
                SecureField("Bearer token", text: $token).textContentType(.password).focused($focused, equals: .token)
            } header: { Text("Private server") } footer: { Text("Both values are stored only in this device’s Keychain. DevLoop requests aggregate dashboard data; it never downloads source code, prompts, diffs, or terminal output.") }
            Section {
                Button { saveAndTest() } label: { HStack { Text("Save & connect"); Spacer(); if saving { ProgressView() } } }.disabled(saving || serverURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if let status { switch status { case .success(let text): Label(text, systemImage: "checkmark.circle.fill").foregroundStyle(DevLoopTheme.mint); case .failure(let text): Label(text, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange) } }
            }
            Section("Connection requirements") {
                Label("HTTPS Tailscale address", systemImage: "lock.fill")
                Label("Bearer authentication", systemImage: "key.fill")
                Label("No analytics or third-party sync", systemImage: "hand.raised.fill")
            }.foregroundStyle(DevLoopTheme.muted)
        }
        .scrollContentBackground(.hidden).background(DevLoopTheme.graphite).navigationTitle("Settings")
        .onAppear { let saved = CredentialStore.shared.load(); serverURL = saved.serverURL; token = saved.token }
    }

    private func saveAndTest() {
        focused = nil; saving = true; status = nil
        Task {
            do {
                let normalized = try await dashboardStore.connect(using: .init(serverURL: serverURL, token: token))
                serverURL = normalized.serverURL
                token = normalized.token
                status = .success("Connected securely")
            } catch { status = .failure(error.localizedDescription) }
            saving = false
        }
    }
}

#Preview { NavigationStack { SettingsView() }.environmentObject(DashboardStore()).preferredColorScheme(.dark) }
