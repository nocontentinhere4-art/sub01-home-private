# Private native phone applications

The phone app producer renders current HomeWorld notes, memories, selected app and battery as a 256×512 English JPEG. It never creates notes or memories. Home, Notes, Memory and Browser are supported; when no actual browser frame exists, Browser says it is unavailable and shows no invented website. App selection changes the phone's in-memory app only, without forcing brain activity or physical phone grip. Existing normal activity updates can select the browser again.

`GET /api/home` exposes `phone_screen` with device, app, frame_id, dimensions, kind and availability. It is null during bathroom privacy. Existing `phone_browser_screen` keeps its original real-browser meaning. Native consumers should prefer `phone_screen`, with the old browser field as a compatibility fallback.

Authenticated `GET /api/home/phone/frame.jpg?frame_id=<current>` requires exact frame identity and returns JPEG, no-store and a pixel ETag; matching If-None-Match receives 304. Authenticated `POST /api/home/phone/action` accepts `{action:"open_app",app:"home"|"notes"|"memory"|"browser",frame_id}` or `{action:"home",frame_id}`. Stale requests and bathroom privacy return 409. Missing operator authentication returns 403. Notes editing remains the existing separately authenticated notes endpoint.

The private authenticated device proxy retains `/devices/phone/frame.jpg` and `/devices/phone/action` and forwards these real routes. Browser navigation remains the existing public-HTTPS validated action, handled by the actual browser service; no browser content is substituted. The producer uses Pillow, also present in the project's numerical/image dependency tree.

Source HTTP tests exercise the registered backend and proxy, real JPEG decode/aspect, ETag, frame invalidation, auth/privacy, real data projection and unchanged saved entries. Runtime/native material and physical hand interaction require separate acceptance. No source test grants physical seating or phone grip.
