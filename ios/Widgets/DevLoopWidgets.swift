import WidgetKit
import SwiftUI

struct DevLoopEntry: TimelineEntry {
    let date: Date
    let cached: CachedDashboard?
    var snapshot: DashboardSnapshot? { cached?.dashboard }
    var isStale: Bool { guard let saved = cached?.savedAt else { return true }; return date.timeIntervalSince(saved) > 60 * 60 * 6 }
}

struct DevLoopProvider: TimelineProvider {
    func placeholder(in context: Context) -> DevLoopEntry { .init(date: Date(), cached: .init(savedAt: Date(), dashboard: DashboardFixture.snapshot)) }
    func getSnapshot(in context: Context, completion: @escaping (DevLoopEntry) -> Void) {
        completion(.init(date: Date(), cached: context.isPreview ? .init(savedAt: Date(), dashboard: DashboardFixture.snapshot) : try? DashboardCache().load()))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<DevLoopEntry>) -> Void) {
        let now = Date(); let entry = DevLoopEntry(date: now, cached: try? DashboardCache().load())
        completion(Timeline(entries: [entry], policy: .after(now.addingTimeInterval(30 * 60))))
    }
}

private struct EmptyWidget: View {
    var compact = false
    var body: some View {
        VStack(spacing: 5) {
            Image(systemName: "circle.hexagongrid").font(compact ? .title3 : .title).foregroundStyle(DevLoopTheme.energy)
            if !compact { Text("Open DevLoop to connect").font(.caption).multilineTextAlignment(.center).foregroundStyle(.secondary) }
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct SmallRingWidgetView: View {
    let entry: DevLoopEntry
    var body: some View {
        Group {
            if let value = entry.snapshot {
                VStack(spacing: 8) {
                    HStack { Text("DEVLOOP").font(.caption2.bold()).foregroundStyle(DevLoopTheme.energy); Spacer(); if entry.isStale { Image(systemName: "clock.badge.exclamationmark").font(.caption2).foregroundStyle(.secondary) } }
                    ZStack {
                        ForEach(Array(value.rings.enumerated()), id: \.element.id) { index, ring in
                            Circle().stroke(Color.white.opacity(0.08), lineWidth: 6)
                            Circle().trim(from: 0, to: ring.progress).stroke(DevLoopTheme.color(for: ring.kind), style: StrokeStyle(lineWidth: 6, lineCap: .round)).rotationEffect(.degrees(-90)).padding(CGFloat(index) * 10)
                        }
                        VStack(spacing: 0) { Text("\(value.streak)").font(.title2.bold()); Image(systemName: "flame.fill").font(.caption).foregroundStyle(DevLoopTheme.energy) }
                    }
                }
            } else { EmptyWidget() }
        }.containerBackground(DevLoopTheme.graphite, for: .widget)
    }
}

struct MediumDashboardWidgetView: View {
    let entry: DevLoopEntry
    var body: some View {
        Group {
            if let value = entry.snapshot {
                HStack(spacing: 18) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("LEVEL \(value.level)").font(.caption2.bold()).foregroundStyle(DevLoopTheme.energy)
                        Text("\(value.xp.formatted())").font(.title.bold())
                        Text("TOTAL XP").font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        Label("\(value.streak) day streak", systemImage: "flame.fill").font(.caption.bold()).foregroundStyle(DevLoopTheme.energy)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: 10) {
                        ForEach(value.rings) { metric in VStack(spacing: 6) { RingView(metric: metric, lineWidth: 7, showLabel: false).frame(width: 55, height: 55).overlay { Text("\(Int(metric.progress * 100))").font(.caption.bold()) }; Text(metric.kind.rawValue.prefix(1).uppercased()).font(.caption2).foregroundStyle(.secondary) } }
                    }
                }.overlay(alignment: .topTrailing) { if entry.isStale { Image(systemName: "clock").font(.caption2).foregroundStyle(.secondary) } }
            } else { EmptyWidget() }
        }.containerBackground(DevLoopTheme.graphite, for: .widget)
    }
}

struct AccessoryCircularView: View {
    let entry: DevLoopEntry
    var body: some View {
        if let metric = entry.snapshot?.time {
            Gauge(value: metric.progress) { Image(systemName: "timer") } currentValueLabel: { Text("\(Int(metric.progress * 100))").font(.caption.bold()) }.gaugeStyle(.accessoryCircular).widgetAccentable()
        } else { Image(systemName: "circle.dashed") }
    }
}

struct AccessoryRectangularView: View {
    let entry: DevLoopEntry
    var body: some View {
        if let value = entry.snapshot {
            VStack(alignment: .leading, spacing: 2) {
                HStack { Label("DevLoop", systemImage: "circle.hexagongrid.fill"); Spacer(); Text("L\(value.level)") }.font(.headline)
                Text("\(Int(value.time.progress * 100))% time · \(Int(value.output.progress * 100))% output")
                Text("\(value.streak) day streak").font(.caption).foregroundStyle(.secondary)
            }.widgetAccentable()
        } else { Text("Open DevLoop to sync").font(.caption) }
    }
}

struct DevLoopRingWidget: Widget {
    let kind = "DevLoopRing"
    var body: some WidgetConfiguration { StaticConfiguration(kind: kind, provider: DevLoopProvider()) { SmallRingWidgetView(entry: $0) }.configurationDisplayName("Daily Rings").description("Your Time, Output, and Consistency loop.").supportedFamilies([.systemSmall]) }
}
struct DevLoopDashboardWidget: Widget {
    let kind = "DevLoopDashboard"
    var body: some WidgetConfiguration { StaticConfiguration(kind: kind, provider: DevLoopProvider()) { MediumDashboardWidgetView(entry: $0) }.configurationDisplayName("Loop Dashboard").description("Level, streak, and daily rings at a glance.").supportedFamilies([.systemMedium]) }
}
struct DevLoopCircularWidget: Widget {
    let kind = "DevLoopCircular"
    var body: some WidgetConfiguration { StaticConfiguration(kind: kind, provider: DevLoopProvider()) { AccessoryCircularView(entry: $0) }.configurationDisplayName("Time Ring").description("Today’s active time progress.").supportedFamilies([.accessoryCircular]) }
}
struct DevLoopRectangularWidget: Widget {
    let kind = "DevLoopRectangular"
    var body: some WidgetConfiguration { StaticConfiguration(kind: kind, provider: DevLoopProvider()) { AccessoryRectangularView(entry: $0) }.configurationDisplayName("Loop Status").description("Your current level, ring progress, and streak.").supportedFamilies([.accessoryRectangular]) }
}

@main struct DevLoopWidgetBundle: WidgetBundle {
    var body: some Widget { DevLoopRingWidget(); DevLoopDashboardWidget(); DevLoopCircularWidget(); DevLoopRectangularWidget() }
}

#Preview(as: .systemSmall) { DevLoopRingWidget() } timeline: { DevLoopEntry(date: .now, cached: .init(savedAt: .now, dashboard: DashboardFixture.snapshot)) }
#Preview(as: .systemMedium) { DevLoopDashboardWidget() } timeline: { DevLoopEntry(date: .now, cached: .init(savedAt: .now, dashboard: DashboardFixture.snapshot)) }
