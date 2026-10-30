# fhir-package-mirror

FHIR package tarballs (`<name>#<version>.tgz`, checked against `SHA512SUMS`) for environments that can't reach packages.fhir.org. `fhir-cache-seed-npm --mirror` in fhir-harness reads them.

Two GitHub Actions do the fetching on a GitHub runner, which can reach hosts that cloud sessions can't. Neither needs anyone's device.

## Adding packages: `mirror.yml`

1. Branch from `main` as `claude/mirror-<topic>`.
2. List the packages in `packages.txt`, one per line, as `name#version`, `name#current` (CI build from `build.fhir.org/ig/qas.json`, with `package/package.json` `version` normalized to `"current"`), `name#1.2.x` (newest match) or `name#latest` (newest release).
3. Push. The run fetches each package and its dependencies from packages.fhir.org. It skips anything already here or on npm at that exact version, and refuses a tarball whose `package/package.json` names a different package or version. Then it adds `SHA512SUMS` lines and commits back to the branch. Results go to `mirror-report.txt` as `ADDED`, `HAVE`, `NPM`, `RANGE`, `LATEST`, `SKIPPED` and `FAILED` lines.
4. Open a PR to `main` and merge it. You can also run the workflow by hand with a package list.

Only exact versions go in. A ballot or npm build is never stored under a release's name.

## Fetching WHO IRIS sources: `iris.yml`

1. Branch as `claude/iris-<topic>`.
2. Write `iris.txt` with lines like these:
   - `fetch <ig> <handle URL>`
   - `fetch-pdf <ig> <handle URL> <pdf name>` (for an item with several PDFs)
   - `search <ig> <query>`
3. Push. The run uses `folio-assistant-core/scripts/fetch-dspace-item.ts` (or `scripts/fetch-dspace-pdf.ts` for `fetch-pdf`). It writes `iris/<ig>/<doc_id>/` with the PDF, `intake.json` and the Dublin Core record, puts search hits in `iris/search.txt`, and records results in `iris/report.txt`.
4. Copy `intake.json` and `<doc_id>.dc.json` into the IG's `uploads/`. Keep the PDFs on the iris branch, which is never merged to `main`. `claude/iris-fetch` holds the sources for bean folio-assistant-53rv.
