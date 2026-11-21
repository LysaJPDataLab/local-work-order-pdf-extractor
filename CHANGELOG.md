# Changelog

## 1.0.0 — Public portfolio edition

- Converted the project into a generic, vendor-neutral work-order PDF extractor.
- Removed all production PDFs, real work-order references, site and asset identifiers, company names, audit results and company-specific setup paths.
- Replaced source-specific tests with synthetic EN / ES / PT fixtures and a temporary PDF generated at test time.
- Changed incremental state keys to paths relative to the input directory.
- Removed absolute source paths and source-document hashes from exported OS records; hashes remain only in the local incremental control file.
- Added repository privacy guidance, release checks and continuous integration.

## Previous development

The parser evolved through experiments with multilingual labels, page continuation, incremental processing and quality flags. Production-specific validation details are intentionally not part of this public repository.
