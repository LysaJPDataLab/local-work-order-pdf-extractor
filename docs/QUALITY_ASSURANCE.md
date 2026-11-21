# Quality assurance

This public edition is validated with synthetic fixtures only. It does not include or require access to production work orders, customer documents, employee data or operational systems.

## Automated coverage

The unit test suite checks:

- Header recognition in English, Spanish and Portuguese.
- Accent- and punctuation-insensitive label matching.
- Continuation-page grouping.
- Extraction of representative fields and event sections.
- Mixed-language structural labels.
- Preservation and flagging of negative durations instead of silent correction.
- Explicit failure when a PDF contains no recognized work-order header.
- Real PDF text extraction using a synthetic PDF created in a temporary directory.
- Incremental processing and idempotent repeat execution.
- Exclusion of absolute input paths and source-document hashes from exported work-order records.

## Reproduce locally

```powershell
python -m unittest discover -s tests -v
python scripts/check_release.py
```

The tests generate temporary PDF files from fabricated text. Temporary files are deleted automatically after each test run.

## Validation boundary

Passing the public tests demonstrates behavior against the documented synthetic fixtures. It does not certify compatibility with every work-order template or prove accuracy on a document the maintainer has not evaluated. New document layouts should be assessed privately by the document owner, then represented in this repository only through fabricated regression fixtures.
