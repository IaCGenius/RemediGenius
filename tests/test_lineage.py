"""Container image, package-origin and runtime lineage (roadmap CE-20)."""
from __future__ import annotations

import pytest

from rgtriage import lineage

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def image(digest=DIGEST, **kw):
    return lineage.Image(digest, **kw)


def test_an_image_is_its_digest_and_tags_stay_labels():
    tagged = lineage.image_from_inspector({"imageId": DIGEST, "platform": "linux/amd64",
                                           "repositoryName": "team/app", "imageTags": ["latest"]})
    assert tagged.digest == DIGEST and tagged.tags == ("latest",)
    assert tagged.entity().key == lineage.Image(DIGEST, platform="linux/amd64", repository="team/app").entity().key
    moved = lineage.image_from_inspector({"imageId": OTHER, "repositoryName": "team/app", "imageTags": ["latest"]})
    assert moved.entity().key != tagged.entity().key  # the same tag on another digest is another image


def test_a_tag_or_a_platform_cannot_be_an_image_identity():
    with pytest.raises(lineage.LineageError, match="immutable sha256"):
        lineage.Image("team/app:latest")
    with pytest.raises(lineage.LineageError):
        lineage.image_from_inspector({"imageId": "", "platform": "linux/amd64"})


def test_package_origin_comes_from_the_installed_path_not_the_name():
    assert lineage.origin_for("/usr/lib/libssl.so") == "base"
    assert lineage.origin_for("/var/lib/dpkg/info/curl.list") == "base"
    assert lineage.origin_for("/app/node_modules/left-pad") == "application"
    assert lineage.origin_for("") == "unknown"
    packages = lineage.packages_from_sbom([
        {"purl": "pkg:apk/openssl@3.1.4", "filePath": "/usr/lib/libssl.so"},
        {"purl": "pkg:npm/left-pad@1.3.0", "filePath": "/app/node_modules/left-pad/index.js"},
    ])
    assert [package.origin for package in packages] == ["base", "application"]
    assert lineage.inherited(packages) == [packages[0]]
    assert lineage.application(packages) == [packages[1]]


def test_lineage_becomes_derived_graph_edges_with_an_approved_version():
    image_ref = image()
    packages = lineage.packages_from_sbom([{"purl": "pkg:apk/openssl@3.1.4", "filePath": "/usr/lib/libssl.so"}])
    workload = lineage.workload_from_inventory({"workload_id": "api", "revision": "42", "account_id": "111122223333",
                                                "region": "us-east-1"})
    edges = lineage.derive(image_ref, packages, [workload], evidence=["sha256:" + "e" * 64])
    assert len(edges) == 2
    assert {edge.predicate for edge in edges} == {"contains", "runs"}
    assert all(edge.status == "derived" and edge.authoritative for edge in edges)
    assert {edge.derivation for edge in edges} == {lineage.DERIVATION_IMAGE_PACKAGE, lineage.DERIVATION_WORKLOAD_IMAGE}


def test_the_same_lineage_twice_is_the_same_edges():
    image_ref = image()
    packages = lineage.packages_from_sbom([{"purl": "pkg:apk/openssl@3.1.4", "filePath": "/usr/lib/libssl.so"}])
    first = [edge.id for edge in lineage.derive(image_ref, packages)]
    second = [edge.id for edge in lineage.derive(image_ref, packages)]
    assert first == second


def test_a_workload_revision_is_part_of_the_identity():
    one = lineage.workload_from_inventory({"workload_id": "api", "revision": "41", "account_id": "111122223333"})
    two = lineage.workload_from_inventory({"workload_id": "api", "revision": "42", "account_id": "111122223333"})
    assert one.entity().key != two.entity().key
    with pytest.raises(lineage.LineageError, match="workload_id and revision"):
        lineage.workload_from_inventory({"workload_id": "api"})


def test_a_platform_is_not_a_base_image_and_no_base_is_invented():
    clarified = lineage.describe_image_context({"repository": "team/app", "tags": ["latest"], "base": "linux/amd64"})
    assert clarified["platform"] == "linux/amd64"
    assert clarified["base"] == "" and clarified["base_known"] is False
    assert clarified["platform_is_not_base"] is True
    with_base = lineage.describe_image_context({"platform": "linux/arm64", "base_image": DIGEST})
    assert with_base["base"] == DIGEST and with_base["base_known"] is True
    tagged_base = lineage.describe_image_context({"platform": "linux/amd64", "base_image": "ubuntu:22.04"})
    assert tagged_base["base"] == "" and tagged_base["base_known"] is False  # a tag is not a base image


def test_collected_findings_no_longer_present_the_platform_as_base():
    import pathlib
    source = pathlib.Path("rgtriage/collect.py").read_text(encoding="utf-8")
    assert '"platform": img.get("platform")' in source
    assert '"base": img.get("platform")' not in source