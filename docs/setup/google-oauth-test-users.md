# Google OAuth Test Users (D-06)

During development and TestFlight, dAIly's Google OAuth consent screen is in
"Testing" mode. Any Google account NOT on the test-users list will see an
"App not verified — this app hasn't been verified by Google" interstitial
when trying to connect Gmail/Calendar.

## Adding a Test User

1. Open https://console.cloud.google.com/apis/credentials/consent
2. Select the dAIly project
3. Scroll to "Test users"
4. Click "+ ADD USERS"
5. Enter the tester's Google email address
6. Save

Limit: Google allows up to 100 test users per app in Testing mode.

## Production (Launch Blocker)

Before public TestFlight release or App Store submission, dAIly must complete
Google's OAuth verification process:

- Submit the OAuth consent screen for verification at
  https://console.cloud.google.com/apis/credentials/consent
- Required for any sensitive scopes (Gmail read/send, Calendar write).
- Verification can take 4–6 weeks; security review for restricted scopes
  (gmail.readonly, gmail.send) takes longer.

This is a launch prerequisite, not a code fix. Track in the production
deploy phase (Phase 23).
