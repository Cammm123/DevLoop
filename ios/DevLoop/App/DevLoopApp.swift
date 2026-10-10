import SwiftUI

@main
struct DevLoopApp: App {
    @StateObject private var store = DashboardStore()
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(store).preferredColorScheme(.dark)
                .task { await store.start() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var store: DashboardStore
    var body: some View {
        TabView {
            NavigationStack { DashboardView() }
                .tabItem { Label("Loop", systemImage: "circle.hexagongrid.fill") }
            NavigationStack { SettingsView() }
                .tabItem { Label("Settings", systemImage: "slider.horizontal.3") }
        }.tint(DevLoopTheme.energy)
    }
}
