# Actual dropped log item rendering

The pinned viewer's WorldView entity packets omit item-stack metadata, and its entity model catalog falls back to a visible magenta box for dropped items. The owned worker now reads the original entity's metadata through the actual version registry and existing prismarine-item decoder. It enriches the same entity packet without changing its ID, position, dimensions or metadata.

A log block item is supported only when its decoded registry name corresponds to a real registered block and the existing viewer package contains both its side and top PNG. The browser retains the upstream item box geometry and transforms, applying those bundled textures with nearest filtering. Unsupported items and failed/missing textures retain a visible fallback. No UUID, production entity ID, spawn position or image is hardcoded; no entity is hidden.

The product frame readiness check waits for actual item metadata and texture loading in addition to terrain meshes, workers and atlas decoding. The product renderer writes a private frame-rendering.json receipt containing actual renderer entity IDs, decoded stack details, rendering status and the captured pixel identity. This receipt is not exposed in public/home state.

Focused CPU checks exercise real registry/Notch decoding, known log and unsupported stick packets, original mesh/position identity, real bundled asset paths, top/side material mapping, texture failure and metadata readiness. Runtime acceptance requires an actual before/after game image and receipt. The saved world and shared PC guest must remain intact across a controlled viewer/backend restart; no autonomous play is claimed while the initial idle frame is cached.
