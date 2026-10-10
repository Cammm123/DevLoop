import SwiftUI
import Charts

struct DashboardView: View {
    @EnvironmentObject private var store: DashboardStore
    var body: some View {
        ZStack {
            DevLoopTheme.graphite.ignoresSafeArea()
            content
        }
        .navigationTitle("DevLoop")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Task { await store.refresh() } } label: {
                    Image(systemName: "arrow.clockwise").rotationEffect(.degrees(store.isRefreshing ? 360 : 0))
                        .animation(store.isRefreshing ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: store.isRefreshing)
                }.disabled(store.isRefreshing)
            }
        }
    }

    @ViewBuilder private var content: some View {
        switch (store.phase, store.snapshot) {
        case (.loading, nil): LoadingDashboard()
        case (.needsSetup, nil): StateView(symbol: "lock.shield", title: "Private by design", message: "Add your Tailscale server and bearer token in Settings.")
        case (.offline(let message), nil): StateView(symbol: "wifi.slash", title: "Can’t reach your loop", message: message)
        case (.empty, let snapshot?): DashboardScroll(snapshot: snapshot, banner: banner("Your loop is ready. Meaningful activity will appear here."))
        case (.offline(let message), let snapshot?): DashboardScroll(snapshot: snapshot, banner: banner("Offline · showing saved data\n\(message)"))
        case (_, let snapshot?): DashboardScroll(snapshot: snapshot, banner: banner(nil))
        default: StateView(symbol: "circle.dashed", title: "No activity yet", message: "Start a coding session to begin your loop.")
        }
    }

    private func banner(_ primary: String?) -> String? {
        let messages = [primary, store.cacheWarning.map { "Widget sync unavailable · \($0)" }].compactMap { $0 }
        return messages.isEmpty ? nil : messages.joined(separator: "\n")
    }
}

private struct DashboardScroll: View {
    @EnvironmentObject private var store: DashboardStore
    let snapshot: DashboardSnapshot; let banner: String?
    var body: some View {
        ScrollView {
            LazyVStack(spacing: 18) {
                if let banner { Text(banner).font(.caption).foregroundStyle(DevLoopTheme.muted).frame(maxWidth: .infinity, alignment: .leading).devLoopCard() }
                HeroView(snapshot: snapshot)
                RingsCard(snapshot: snapshot)
                SummaryCard(summary: snapshot.summary)
                TrendCard(points: snapshot.trend)
                DistributionCard(title: "Languages", symbol: "chevron.left.forwardslash.chevron.right", items: snapshot.languages)
                DistributionCard(title: "Projects", symbol: "folder.fill", items: snapshot.projects)
                QuestsCard(quests: snapshot.quests)
                AchievementsCard(items: snapshot.achievements)
            }.padding(16)
        }.refreshable { await store.refresh() }
    }
}

private struct SummaryCard: View {
    let summary: DailySummary
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]
    var body: some View {
        LazyVGrid(columns: columns, spacing: 12) {
            StatCell(value: "\(summary.activeMinutes)", label: "active min", symbol: "timer")
            StatCell(value: "\(summary.commits)", label: "commits", symbol: "arrow.triangle.branch")
            StatCell(value: "\(summary.successfulChecks)", label: "green checks", symbol: "checkmark.seal.fill")
            StatCell(value: "\(summary.focusSessions)", label: "focus sessions", symbol: "moon.stars.fill")
        }.devLoopCard()
    }
}

private struct StatCell: View {
    let value: String; let label: String; let symbol: String
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).foregroundStyle(DevLoopTheme.energy).frame(width: 24)
            VStack(alignment: .leading, spacing: 1) { Text(value).font(.title3.bold()); Text(label).font(.caption2).foregroundStyle(DevLoopTheme.muted) }
            Spacer(minLength: 0)
        }.padding(10).background(DevLoopTheme.raised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct HeroView: View {
    let snapshot: DashboardSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) { Text("LEVEL \(snapshot.level)").font(.caption.weight(.bold)).foregroundStyle(DevLoopTheme.energy); Text("\(snapshot.xp.formatted()) XP").font(.largeTitle.bold()) }
                Spacer(); Label("\(snapshot.streak) day streak", systemImage: "flame.fill").foregroundStyle(DevLoopTheme.energy).font(.subheadline.weight(.semibold))
            }
            ProgressView(value: snapshot.levelProgress).tint(DevLoopTheme.energy)
            HStack { Text("\(snapshot.xpInLevel) / \(snapshot.xpForNextLevel) to next level"); Spacer(); Text(snapshot.generatedAt, style: .relative) }.font(.caption).foregroundStyle(DevLoopTheme.muted)
        }.devLoopCard()
    }
}

private struct RingsCard: View {
    let snapshot: DashboardSnapshot
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Today’s loop", systemImage: "scope").font(.headline)
            HStack(spacing: 14) {
                ForEach(snapshot.rings) { metric in VStack(spacing: 10) { RingView(metric: metric, lineWidth: 9).frame(height: 88); Text(metric.kind.rawValue.capitalized).font(.caption.weight(.semibold)) } }
            }
            Text(snapshot.goals.insight).font(.caption).foregroundStyle(DevLoopTheme.muted)
        }.devLoopCard()
    }
}

private struct TrendCard: View {
    let points: [TrendPoint]
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("14-day rhythm", systemImage: "chart.xyaxis.line").font(.headline)
            if points.isEmpty { EmptyRow(text: "Your activity trend will grow here.") }
            else { Chart(points) { point in AreaMark(x: .value("Day", point.date), y: .value("Minutes", point.activeMinutes)).foregroundStyle(LinearGradient(colors: [DevLoopTheme.energy.opacity(0.38), .clear], startPoint: .top, endPoint: .bottom)); LineMark(x: .value("Day", point.date), y: .value("Minutes", point.activeMinutes)).foregroundStyle(DevLoopTheme.energy).interpolationMethod(.catmullRom) }.chartXAxis { AxisMarks(values: .stride(by: .day, count: 4)) { _ in AxisValueLabel(format: .dateTime.weekday(.narrow)); AxisGridLine().foregroundStyle(Color.white.opacity(0.05)) } }.chartYAxis(.hidden).frame(height: 150) }
        }.devLoopCard()
    }
}

private struct DistributionCard: View {
    let title: String; let symbol: String; let items: [DistributionItem]
    private var total: Double { max(items.reduce(0) { $0 + $1.value }, 1) }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(title, systemImage: symbol).font(.headline)
            if items.isEmpty { EmptyRow(text: "No \(title.lowercased()) recorded yet.") }
            ForEach(Array(items.prefix(5).enumerated()), id: \.element.id) { index, item in
                VStack(spacing: 6) { HStack { Text(item.name).lineLimit(1); Spacer(); Text(item.value / total, format: .percent.precision(.fractionLength(0))).foregroundStyle(DevLoopTheme.muted) }; GeometryReader { proxy in ZStack(alignment: .leading) { Capsule().fill(Color.white.opacity(0.07)); Capsule().fill(index == 0 ? DevLoopTheme.energy : DevLoopTheme.mint.opacity(0.75)).frame(width: proxy.size.width * item.value / total) } }.frame(height: 5) }.font(.subheadline)
            }
        }.devLoopCard()
    }
}

private struct QuestsCard: View {
    let quests: [Quest]
    var body: some View { VStack(alignment: .leading, spacing: 14) { Label("Quests", systemImage: "flag.checkered").font(.headline); if quests.isEmpty { EmptyRow(text: "New sustainable goals arrive soon.") }; ForEach(quests) { quest in VStack(alignment: .leading, spacing: 7) { HStack { Text(quest.title).font(.subheadline.weight(.medium)); Spacer(); Text("\(quest.current.formatted()) / \(quest.target.formatted()) \(quest.unit)").font(.caption).foregroundStyle(DevLoopTheme.muted) }; ProgressView(value: quest.progress).tint(DevLoopTheme.energy) } } }.devLoopCard() }
}

private struct AchievementsCard: View {
    let items: [Achievement]
    var body: some View { VStack(alignment: .leading, spacing: 14) { Label("Recent achievements", systemImage: "sparkles").font(.headline); if items.isEmpty { EmptyRow(text: "Milestones will be celebrated here.") }; ForEach(items.prefix(4)) { item in HStack(spacing: 12) { Image(systemName: item.symbol).foregroundStyle(DevLoopTheme.energy).frame(width: 30, height: 30).background(DevLoopTheme.energy.opacity(0.1), in: Circle()); VStack(alignment: .leading) { Text(item.title).font(.subheadline.weight(.semibold)); Text(item.detail).font(.caption).foregroundStyle(DevLoopTheme.muted) }; Spacer(); Text(item.unlockedAt, style: .relative).font(.caption2).foregroundStyle(.secondary) } } }.devLoopCard() }
}

private struct EmptyRow: View { let text: String; var body: some View { Text(text).font(.subheadline).foregroundStyle(DevLoopTheme.muted).frame(maxWidth: .infinity, minHeight: 50) } }
private struct StateView: View { let symbol: String; let title: String; let message: String; var body: some View { ContentUnavailableView(title, systemImage: symbol, description: Text(message)) } }
private struct LoadingDashboard: View { var body: some View { ScrollView { VStack(spacing: 18) { ForEach(0..<4) { _ in RoundedRectangle(cornerRadius: 22).fill(DevLoopTheme.surface).frame(height: 150).overlay { ProgressView().tint(DevLoopTheme.energy) }.redacted(reason: .placeholder) } }.padding() } } }

#Preview { NavigationStack { DashboardView() }.environmentObject(DashboardStore(preview: DashboardFixture.snapshot)).preferredColorScheme(.dark) }
