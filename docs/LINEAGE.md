# Container and workload lineage

Grouping Inspector findings by package *name* cannot establish a shared base-image cause. Two packages with the same name
can come from different layers, and a moving tag is not an identity. Lineage here is normalised from what the collectors
already return, and it feeds the operational graph (CE-19).

## Identities

| Thing | Identity | Notes |
| --- | --- | --- |
| Image | `sha256:` digest | `repository` and `tags` are labels; the same tag on another digest is another image |
| Package | `purl` or `cpe` | plus the installed path, which decides its origin |
| Workload revision | `workload_id@revision`, scoped by account and region | a rollback or a new revision is a different entity |

A tag, a platform string or a repository name is refused as an identity: `Image` raises rather than guessing.

## Package origin

`origin_for(path)` classifies the installed path: base-image paths (`/usr/`, `/bin/`, `/lib/`, `...`) are **base**,
anything else is **application**, and no path means **unknown**. That distinction is what makes "patch the application"
different from "rebuild the base image", and `inherited()` / `application()` expose the two sets.

Origin is never inferred from the package name.

## Platform is not a base image

Findings collected before this change stored the runtime platform in `context.image.base`. `collect.py` now writes
`platform` and an empty `base` with `base_known: false`, and `describe_image_context()` clarifies older rows the same
way: a base image is only claimed when a `sha256:` digest of one was actually observed. A tag in that field is dropped.

## Derived edges

`derive(image, packages, workloads)` returns CE-19 assertions:

- `image contains package` — `ce.image-contains-package/v1`
- `workload runs image` — `ce.workload-runs-image/v1`

Both are `derived` (never `observed`), carry the derivation version, and are deterministic: the same lineage produces the
same assertion ids, so replaying ingestion cannot duplicate edges.

## What this does not do

It does not read the SBOM or the inventory from AWS by itself, and it does not claim a base image from a platform, a tag
or a naming convention. The collector supplies the records; a missing digest is an error, not a guess.