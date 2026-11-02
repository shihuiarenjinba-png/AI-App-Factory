# Image delivery HTML: market rationale and gate (2026-11-02)

## Competitive evidence checked 2026-11-02

- WinMerge, free/open source, offers folder comparison and visual image comparison: https://www.winmerge.io/features.html and https://manual.winmerge.org/en/Compare_dirs.html
- Beyond Compare (commercial) already supports HTML and plain-text comparison reports: https://documentation.help/BeyondCompare4/dlgreport.html
- Beyond Compare picture compare supports visual image comparison: https://documentation.help/BeyondCompare4/viewpix.html

**Implication:** Neither file comparison nor HTML output alone justifies a paid app. The specific buyer hypothesis is that a nontechnical client receiving revised image assets values a self-contained, offline, readable change explanation with small SHA-verified previews and explicit limits, without installing a diff tool or exposing a folder tree. This is a hypothesis, not validated differentiation.

## Implemented this revision

- Step-three HTML export is primary; existing TXT/CSV/JSON preserved.
- Local embedded previews for verified small images; no network/script dependencies; escaped filenames.
- Before image never fabricated if baseline only has hash/metadata; after file must still match SHA at export.
- Source file unchanged, bounded previews/HTML, safe output outside both scanned folders.
- EN/JA and hosted Windows DPI/packaged EXE regression are required.

## Commercial gate unchanged

Score 64/100, independent real buyers 0/5, why_pay_verified=false. Synthetic demos and cloud EXE replay are not human purchase evidence. Keep MARKET_FIT_HOLD, no promotion, Identity rebind, commercial MSIX or Store action. Recruit five independent first-time buyers to compare free tools vs this exact EXE on time-to-deliver, errors, recipient comprehension and actual willingness to pay; record only real observations.
