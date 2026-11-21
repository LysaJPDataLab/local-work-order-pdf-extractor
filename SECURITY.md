# Security and privacy

This repository is intended for public portfolio use and contains generic code plus synthetic tests only.

## Do not commit

- Source PDFs or scanned pages.
- JSON, CSV, logs or incremental state generated from real documents.
- Customer, supplier, employer, site, equipment, employee or work-order identifiers.
- Credentials, access tokens, private keys, `.env` files or personal computer paths.

The `.gitignore` excludes common local artifacts, but ignore rules are not a security boundary. Review every staged file before pushing.

## Local processing

The application reads files from the local filesystem and writes output locally. It does not implement network requests, telemetry or API integrations. Installing dependencies requires the normal package manager workflow and access to the configured Python package index.

## Reporting an issue

For security concerns in this public code, open a GitHub issue without attaching confidential documents, screenshots, logs or private data. Describe the issue using fabricated examples.
