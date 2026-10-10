# DevLoop for iPhone

Native iOS 17 SwiftUI dashboard and WidgetKit extension. The app reads only
aggregate dashboard data from `GET {server}/v1/dashboard` with bearer auth.
Server URL and token are stored in Keychain; widgets read an aggregate snapshot
from the `group.com.cameronkani.devloop` App Group.

## Generate and run

1. Install XcodeGen (`brew install xcodegen`).
2. Run `python3 Scripts/generate_app_icon.py` if regenerating the icon.
3. Run `xcodegen generate`, open `DevLoop.xcodeproj`, and select your signing team.
4. Enable the App Group on both targets in your Apple developer account.
5. Build the `DevLoop` scheme for an iOS 17+ iPhone.

No development team or credential is checked into source.