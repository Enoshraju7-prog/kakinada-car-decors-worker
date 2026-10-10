# Mobile release plan - deferred

Agreed direction: partners and staff only, invitation-based access, Android and iOS using Capacitor to reuse React with the current FastAPI/PostgreSQL backend. Neither store developer account has been created. This document records the plan; mobile implementation has not started.

1. Add mobile navigation, camera/PDF upload and secure mobile authentication. First release stays online-only; no offline stock ledger.
2. Test receiving, sales, receipt printing/sharing, customer privacy, retries, expired sessions and interrupted connections on Android/iPhone. AI keys remain server-side.
3. Enosh completes developer enrollment/verification. Prepare signed builds, KCD assets, support/privacy pages, data disclosures and synthetic reviewer access.
4. Run partner testing first, then submit to the stores. Recheck fees and policies before enrollment/release. The researched baseline was Google $25 once, Apple $99/year with regional pricing, and 12 opted-in testers for 14 continuous days for new Google personal accounts. Store approval is not guaranteed.

Sources: [Capacitor](https://capacitorjs.com/docs), [Google enrollment](https://support.google.com/googleplay/android-developer/answer/6112435), [Google testing](https://support.google.com/googleplay/android-developer/answer/14151465), [Apple enrollment](https://developer.apple.com/programs/enroll/), [Apple review](https://developer.apple.com/app-store/review/guidelines/).
