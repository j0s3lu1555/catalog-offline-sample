# Offline catalog facts: a small Python work sample

A reproducible, standard-library Python 3.9+ demonstration prepared for Jose Mendez’s Catalog Desk project with AI assistance. This is original demonstration software, not a client case study, a university partnership or an official Coursedog integration.

It extracts a course identifier, displayed title and explicit minimum/maximum credits from one supported rendered HTML template. Unsupported or conflicting records go into a review queue. IDs retain leading zeros, source bytes receive a SHA-256 hash, and catalog year remains unknown unless independently established.

## Run the fictional example

```sh
python3 catalog_extract.py manifest.json > result.json
python3 -m unittest -v test_catalog_extract.py
```

The sample files named `fixture-*.html` are authored fictional examples at `example.edu`, not real university records. The manifest has no observation timestamps: these are authored fixtures, not observations of a university site. `example-output.json` is the actual generated result.

## Boundaries

- Offline only: the extractor makes no network calls and has no credentials or paid API dependencies.
- This adapter supports one narrow HTML shape. A matching Nuxt marker alone does not establish vendor identity; use only on documents independently known to match the intended template.
- The output includes a source URL and content hash, not proof that the website actually served those bytes. Collection provenance must be independently verified.
- Missing fields, inconsistent headings, credit contradictions and duplicate codes within an institution require review. No fuzzy guesses or silent merges.
- No prerequisite interpretation, JSON-LD extraction, Acalog support, catalog-wide crawl or production deployment is claimed.
- Do not supply private student data or credentials. The demo does not export spreadsheets; treat all text as text in any downstream spreadsheet to prevent formula interpretation.
- Python 3.9 and the included 21 test methods were checked locally on macOS. Other platforms are not certified.

The historical adapter name in JSON is `coursedog-rendered-course-v1`. It denotes the narrow adapter being demonstrated, not vendor certification.

## Commercial work

For a proposed paid task, agree the authorized source set, output schema, review policy, acceptance examples, deadline and payment route before work starts. This repository grants no ongoing service commitment.

Contact: joserecoverydesk@gmail.com
