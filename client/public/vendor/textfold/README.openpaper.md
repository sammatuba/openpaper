# Textfold reader vendoring

Source: https://github.com/chenxiachan/textfold
Pinned commit: 92ad625ab6887bf0060374c1fd86a558513baed2
License: Apache-2.0. Original LICENSE and NOTICE are included unchanged.

The source was cloned with `git clone --depth 1 --filter=blob:none --no-checkout`.
Only the browser reader assets were checked out; no desktop app or model bridge
is installed. reader.css, i18n.js and template.html are exact upstream copies.
reader.js is upstream's real word-morph, keyframe/gesture, paragraph, map, notes
and settings engine, with one small public-format compatibility extension:
`lad.take` may contain independent Takeaway tokens when Key does not start with
that sentence. Selection, note anchors, restoration and highlighting use that same
level-specific line. The upstream fallback is unchanged when `lad.take` is absent,
and the shared-prefix path retains upstream word identities.
The exact diff is `openpaper-takeaway.patch`; changed-file notices are at its top.

`UPSTREAM.json` records source paths, upstream SHA-256 and shipped SHA-256 values.
Run `node scripts/check-textfold-vendor.cjs` from client to verify shipped bytes.
To update: fetch a chosen upstream commit, copy the same files and licenses,
apply/rebase the recorded patch, update both sets of hashes, then run parser,
production-build and real-engine browser checks. Do not silently edit vendored
assets. Keep the source commit and license/notice with every redistribution.

OpenPaper's adapter is `src/lib/textfold-upstream.tsx`; the React host is
`src/components/textfold/TextFoldReader.tsx`. Source HTML is produced through
OpenPaper's safe Markdown renderer, document IDs are mapped to safe internal IDs,
roles are allowlisted, template insertion is one-pass, and JSON escapes opening
angle brackets. A frame policy prevents outbound requests. Canonical source,
sentence anchors and provenance remain in the saved textfold/doc document.
The engine's browser-local notes are namespaced by signed-in user, document and source-version hash.
Unconnected model actions are hidden; project chat uses OpenPaper's composer.

This directory does not include Textfold's vendor fonts, math/PDF renderers,
media assets or standalone Python service. System-font fallbacks are used.
