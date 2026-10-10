# DevLoop for iPhone

Native iOS 17 SwiftUI dashboard and WidgetKit extension. The app reads only aggregate dashboard data from `GET {server}/v1/dashboard` with bearer authentication. The server URL and token are stored in Keychain; widgets read an aggregate snapshot from a shared App Group container.

## Before generating the project

The checked-in identifiers are working examples from the original deployment. Every fork must replace:

- `DEVELOPMENT_TEAM` and all bundle identifiers in `project.yml`.
- The App Group in both `.entitlements` files.
- `DashboardCache.appGroup` in `Shared/Storage/DashboardCache.swift`.
- The Keychain service name in `DevLoop/Services/CredentialStore.swift`.

Register the new App Group in the Apple Developer portal and attach it to both the main app and widget App IDs. Creating the group without attaching it to both IDs is insufficient.

See the root [`README.md`](../README.md) for exact values, portal steps, server deployment, Tailscale configuration, and troubleshooting.

## Generate, test, and run

1. Install XcodeGen: `brew install xcodegen`.
2. Run `python3 Scripts/generate_app_icon.py` only when regenerating the icon.
3. Run `xcodegen generate`.
4. Open `DevLoop.xcodeproj` and confirm signing/App Group capabilities for both targets.
5. Build the `DevLoop` scheme for an iOS 17+ iPhone.

Run tests with an installed simulator name:

```bash
xcodebuild -project DevLoop.xcodeproj -scheme DevLoop \
  -destination 'platform=iOS Simulator,name=iPhone 16' test
```

No API token, server URL, provisioning profile, certificate, or private key is checked into source.
