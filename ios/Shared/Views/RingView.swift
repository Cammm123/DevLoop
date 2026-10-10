import SwiftUI

struct RingView: View {
    let metric: RingMetric
    var lineWidth: CGFloat = 12
    var showLabel = true

    var body: some View {
        ZStack {
            Circle().stroke(Color.white.opacity(0.08), lineWidth: lineWidth)
            Circle().trim(from: 0, to: metric.progress)
                .stroke(DevLoopTheme.color(for: metric.kind), style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: DevLoopTheme.color(for: metric.kind).opacity(0.28), radius: 8)
            if showLabel {
                VStack(spacing: 2) {
                    Text(metric.value, format: .number.precision(.fractionLength(metric.value.rounded() == metric.value ? 0 : 1))).font(.system(size: 22, weight: .bold, design: .rounded))
                    Text(metric.unit.uppercased()).font(.system(size: 8, weight: .semibold)).foregroundStyle(.secondary)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(metric.kind.rawValue), \(Int(metric.progress * 100)) percent")
    }
}
