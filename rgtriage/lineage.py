"""Container image, package-origin and runtime lineage (roadmap CE-20).

Grouping Inspector findings by package *name* cannot establish a shared base-image cause: two packages with the same
name can come from different layers, and a moving tag is not an identity. This module normalises what the collectors
already return into immutable, scoped lineage:

- an image is its digest (a tag is kept as a label, never as identity);
- a package is its `purl`/`cpe` plus the layer it was installed in (`base`, `application`, `unknown`);
- a workload revision points at the image it actually runs, from the inventory receipt rather than from a finding.

`derive()` turns that into CE-19 assertions, so the graph gets `image contains package` and `workload runs image` edges
with the approved derivation version and no invented provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import relationships as graph

DERIVATION_IMAGE_PACKAGE = "ce.image-contains-package/v1"
DERIVATION_WORKLOAD_IMAGE = "ce.workload-runs-image/v1"
ORIGINS = ("base", "application", "unknown")
# Where AWS base images install packages. Anything outside these prefixes came from the application layer.
BASE_PATHS = ("/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/etc/", "/var/lib/rpm", "/var/lib/dpkg")


class LineageError(ValueError):
    """A lineage input cannot be normalised without inventing something."""


def _digest(value: str, what: str) -> str:
    text = str(value or "")
    if not text.startswith("sha256:") or len(text) != 71:
        raise LineageError(f"{what} needs an immutable sha256: digest, got {text[:40]!r}")
    return text


@dataclass(frozen=True)
class Image:
    """An immutable image. `tags` and `repository` are labels; they are never part of the identity."""

    digest: str
    platform: str = ""
    repository: str = ""
    tags: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "digest", _digest(self.digest, "an image"))

    def entity(self) -> graph.Entity:
        return graph.image_entity(self.digest, platform=self.platform, registry=self.repository)


@dataclass(frozen=True)
class Package:
    """A package plus where it came from. `origin` decides whether it is inherited or application-installed."""

    purl: str
    path: str = ""
    origin: str = "unknown"

    def __post_init__(self):
        if not self.purl.startswith(("pkg:", "cpe:")):
            raise LineageError(f"a package needs a purl or cpe identity, got {self.purl[:40]!r}")
        if self.origin not in ORIGINS:
            raise LineageError(f"origin must be one of {', '.join(ORIGINS)}")

    def entity(self) -> graph.Entity:
        return graph.package_entity(self.purl)


@dataclass(frozen=True)
class Workload:
    """What is actually deployed: a revision of a workload, running one image."""

    workload_id: str
    revision: str
    account_id: str
    region: str
    resource_type: str = "ecs-service"

    def entity(self) -> graph.Entity:
        return graph.scoped_entity("workload", f"{self.workload_id}@{self.revision}",
                                   account_id=self.account_id, region=self.region,
                                   resource_type=self.resource_type)


def origin_for(path: str) -> str:
    """Base-image paths are inherited; anything else is application-installed. Unknown when there is no path."""
    if not path:
        return "unknown"
    return "base" if str(path).startswith(BASE_PATHS) else "application"


def image_from_inspector(record: dict) -> Image:
    """Normalise an Inspector image record. The digest is required; the platform is a platform, not a base image."""
    image_id = record.get("imageId") or record.get("image_id") or ""
    return Image(digest=_digest(image_id, "an Inspector image"),
                 platform=str(record.get("platform") or ""),
                 repository=str(record.get("repositoryName") or record.get("repository") or ""),
                 tags=tuple(record.get("imageTags") or ()))


def packages_from_sbom(packages) -> list:
    """Normalise a package inventory; origin comes from the installed path, never from a guess about the name."""
    out = []
    for item in packages:
        purl = item.get("purl") or item.get("packageManager", "") + ":" + str(item.get("name") or "")
        if not purl.startswith(("pkg:", "cpe:")):
            raise LineageError(f"package {item.get('name')!r} has no purl identity")
        path = str(item.get("filePath") or item.get("path") or "")
        out.append(Package(purl=purl, path=path, origin=item.get("origin") or origin_for(path)))
    return out


def workload_from_inventory(receipt: dict) -> Workload:
    """A runtime inventory receipt says what runs: the workload revision and the image digest it is running."""
    if not receipt.get("workload_id") or not receipt.get("revision"):
        raise LineageError("an inventory receipt needs workload_id and revision")
    return Workload(workload_id=str(receipt["workload_id"]), revision=str(receipt["revision"]),
                    account_id=str(receipt.get("account_id") or ""), region=str(receipt.get("region") or ""),
                    resource_type=str(receipt.get("resource_type") or "ecs-service"))


def derive(image: Image, packages, workloads=(), *, evidence=()) -> list:
    """The graph edges for this lineage, all `derived` under the approved versions."""
    assertions = [graph.Assertion(image.entity(), "contains", package.entity(), status="derived",
                                  derivation=DERIVATION_IMAGE_PACKAGE, evidence=tuple(evidence))
                  for package in packages]
    for workload in workloads:
        assertions.append(graph.Assertion(workload.entity(), "runs", image.entity(), status="derived",
                                         derivation=DERIVATION_WORKLOAD_IMAGE, evidence=tuple(evidence)))
    return assertions


def inherited(packages) -> list:
    """Packages that came from the base image: patching the application cannot fix these."""
    return [package for package in packages if package.origin == "base"]


def application(packages) -> list:
    return [package for package in packages if package.origin == "application"]


def describe_image_context(context: dict) -> dict:
    """Clarify the old `context.image` shape: a platform is not a base image, and no base image is claimed without one.

    Findings collected before this change carry `base = platform`. That value is moved to `platform`, `base` becomes
    empty, and `base_known` says whether a real base-image digest was observed.
    """
    image = dict(context or {})
    platform = image.get("platform") or image.get("base") or ""
    base = image.get("base_image") or ""
    if base and not str(base).startswith("sha256:"):
        base = ""  # a tag or a platform string is not a base image
    return {"repository": image.get("repository") or "", "tags": list(image.get("tags") or []),
            "platform": platform, "base": base, "base_known": bool(base),
            "platform_is_not_base": True}