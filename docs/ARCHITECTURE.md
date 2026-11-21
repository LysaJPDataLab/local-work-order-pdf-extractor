# Architecture notes

## Processing stages

1. **Discovery:** enumerate PDF files under the configured local input folder.
2. **Fingerprinting:** compute file size, modification time and SHA-256 for local incremental decisions.
3. **Text extraction:** use PyMuPDF to read selectable text page by page.
4. **Label normalization:** remove diacritics and normalize case and punctuation for comparisons only. Source values remain unchanged.
5. **Page grouping:** detect the start of a work order and attach following continuation pages until the next recognized header.
6. **Field parsing:** extract configured aliases, structured stop events, alarm rows, failure descriptors and operational numeric values.
7. **Quality review:** expose missing fields, unrecognized sections and suspicious duration values as flags.
8. **Export:** write consolidated JSON and CSV atomically.

## Design decisions

- **Local-first:** no network client or remote destination is implemented.
- **Explicit aliases:** structural labels are configured in dictionaries, making supported variants inspectable and testable.
- **No silent repair:** dates and unusual duration values are not rewritten based on assumptions.
- **Conservative tables:** labor, materials and tools remain textual where plain-text extraction cannot reliably reconstruct merged cells.
- **Incremental idempotency:** input-relative paths and file fingerprints prevent repeated work while avoiding absolute computer paths in the state file.
- **Synthetic tests:** all test records are fabricated and generated locally; no production data is required.

## Extension points

- Add a language alias to `LABELS_BY_LANGUAGE` or `FIELD_ALIASES` and a regression test using fabricated text.
- Add coordinate-aware table extraction as an optional parser stage.
- Add OCR only as an explicitly configured local fallback for scanned documents, with separate quality flags.
- Add schema versioning before making incompatible changes to JSON output.
