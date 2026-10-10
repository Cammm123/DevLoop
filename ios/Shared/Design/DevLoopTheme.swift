import SwiftUI

enum DevLoopTheme {
    static let graphite = Color(red: 0.035, green: 0.043, blue: 0.047)
    static let surface = Color(red: 0.075, green: 0.086, blue: 0.09)
    static let raised = Color(red: 0.105, green: 0.118, blue: 0.12)
    static let energy = Color(red: 0.72, green: 0.96, blue: 0.20)
    static let mint = Color(red: 0.23, green: 0.85, blue: 0.59)
    static let cyan = Color(red: 0.23, green: 0.72, blue: 0.87)
    static let muted = Color.white.opacity(0.58)
    static let ringGradient = AngularGradient(colors: [energy, mint, energy], center: .center)

    static func color(for kind: RingMetric.Kind) -> Color {
        switch kind { case .time: energy; case .output: mint; case .consistency: cyan }
    }
}

struct CardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(16).background(DevLoopTheme.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.white.opacity(0.055)))
    }
}
extension View { func devLoopCard() -> some View { modifier(CardModifier()) } }
