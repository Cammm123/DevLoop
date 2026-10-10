# DevLoop

A private coding-fitness tracker for Mac, Linux, and iPhone.

DevLoop tracks development metadata—not source code—and turns active time, meaningful output, and consistency into rings, XP, streaks, quests, achievements, trends, and widgets.

## Repository

- `server/` private API and analytics
- `collector/` Mac/Linux telemetry collector
- `ios/` native SwiftUI app and WidgetKit extension
- `docs/architecture.md` privacy, event contract, and topology

All network communication is intended to stay on Cameron's Tailscale network.
