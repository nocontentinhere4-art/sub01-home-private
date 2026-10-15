# Private native phone applications

The phone app producer renders current HomeWorld notes, memories, selected app and battery as a 256×512 English JPEG. It never creates notes or memories. Home, Notes, Memory and Browser are supported; when no actual browser frame exists, Browser says it is unavailable and shows no invented website. App selection changes the phone's in-memory app only, without forcing brain activity or physical phone grip. Explicit operator app selection holds through phone ticks and background browser-page updates. Leaving the actual phone activity releases that ownership; only an actual new phone navigation or explicit app/navigation action selects Browser, never a timer/default screen. Restoring a saved app does not restore a previous operator session lock.

`GET /api/home` exposes `phone_screen` with device, app, frame_id, dimensions, kind and availability. It is null during bathroom privacy. Existing `phone_browser_screen` keeps its original real-browser meaning. Native consumers should prefer `phone_screen`, with the old browser field as a compatibility fallback.

Authenticated `GET /api/home/phone/frame.jpg?frame_id=<current>` requires exact frame identity and returns JPEG, no-store and a pixel ETag; matching If-None-Match receives 304. Authenticated `POST /api/home/phone/action` accepts `{action:"open_app",app:"home"|"notes"|"memory"|"browser",frame_id}` or `{action:"home",frame_id}`. Stale requests and bathroom privacy return 409. Missing operator authentication returns 403. Notes editing remains the existing separately authenticated notes endpoint.

The private authenticated device proxy retains `/devices/phone/frame.jpg` and `/devices/phone/action` and forwards these real routes. Browser navigation remains the existing public-HTTPS validated action, handled by the actual browser service; no browser content is substituted. The producer uses Pillow, also present in the project's numerical/image dependency tree.

Source HTTP tests exercise the registered backend and proxy, real JPEG decode/aspect, ETag, frame invalidation, auth/privacy, real data projection and unchanged saved entries. Runtime/native material and physical hand interaction require separate acceptance. No source test grants physical seating or phone grip.

Notes writes use the same authenticated proxy route with `{action:"save_note",frame_id,title?,text}`. The current app must be Notes. Title is optional, at most 120 characters; trimmed title and nonempty text together must fit the existing 2000-character note limit. The proxy forwards only these note fields to `/api/home/phone/action`, never to PC keyboard or browser input. Request bodies are bounded to 4096 bytes, including streamed bodies. The backend invokes the real HomeWorld.add_note and awaits the existing private save_state; successful writes return the next phone frame identity. Retrying an old frame cannot duplicate the note. Source HTTP tests use isolated fixture worlds and temporary save files, never owner notes. Native text entry and deployed runtime acceptance remain separate.

Phone selection has an independent persisted phone_selection_revision, included in its frame identity without changing the actor route sequence. Repeating an identical app selection reports changed:false and leaves its frame unchanged. Session exit invalidates the old composer frame; a restored app retains its revision but not an operator lock or prior navigation notification. The actual Live.on_screen hook only forwards a phone navigation when ScreensStatus.seen recognizes a new page, so same-URL frame repaints cannot replace Notes. Explicit authenticated successful operator navigation deliberately supersedes the composer; an unavailable/failed browser does not.

With an actual browser source, the generic phone frame identity binds phone selection revision plus the raw browser frame identity. Same-source title/age repaints do not invalidate it. The backend reads the actual raw source frame internally; legacy `/api/screen/phone.jpg` and direct browser-action clients retain their original raw-frame contract. The private proxy translates approved generic browser actions to raw IDs and includes a phone_frame_id context check so an app selection change between its state GET and action POST is rejected by the actual backend before browser input. Restarting/missing browser sources render the truthful unavailable app with a stable identity. Tests use explicitly labeled fixture browser images and IDs, never claim them as production website evidence.

Native address entry (source, not runtime acceptance): with the actual phone
focused and Browser selected (4), release B to open the English address editor.
Enter submits a public HTTPS URL through the existing authenticated proxy with
the current painted phone frame identity; Esc closes and retains the draft.
The pawn receives UI-only input while editing. Opening is confirmed only by
HTTP200 plus ok:true; failures retain the address. Closing invalidates late
replies, app changes close the editor, and privacy erases its text and widget.
Browser navigation has a bounded30s proxy/35s native timeout, while ordinary
state/frame/action polling retains its existing shorter deadlines. Public URL,
no-local-address and downstream browsing restrictions remain authoritative.
The private viewer supports physical Arrow/Home/End/Tab/Delete keys so phone
scrolling and text widgets can receive their existing native bindings. This
adds no Ctrl/Alt/Meta host shortcuts or browser credentials.
