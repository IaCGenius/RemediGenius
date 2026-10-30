"""The deployment split, the baked image and the parking tool (offline; no AWS calls)."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


@pytest.fixture(scope="module")
def host():
    spec = importlib.util.spec_from_file_location("spot_host", ROOT / "deploy/aws-single/host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(*parts):
    return (DEPLOY.joinpath(*parts)).read_text(encoding="utf-8")


# ------------------------------------------------------------------ one version everywhere

VERSION_FILES = (
    ("pyproject.toml", r'^version = "([^"]+)"'),
    ("profiles/remedigenius/distribution.yaml", r"^version:\s*\"?([0-9.]+)\"?\s*$"),
    ("profiles/remedigenius/plugins/rg-triage/plugin.yaml", r"^version:\s*\"?([0-9.]+)\"?\s*$"),
    ("profiles/remedigenius/dashboard-plugins/rg-knowledge/plugin.yaml", r"^version:\s*\"?([0-9.]+)\"?\s*$"),
    ("profiles/remedigenius/dashboard-plugins/rg-github/plugin.yaml", r"^version:\s*\"?([0-9.]+)\"?\s*$"),
    ("profiles/remedigenius/dashboard-plugins/rg-board/plugin.yaml", r"^version:\s*\"?([0-9.]+)\"?\s*$"),
    ("profiles/remedigenius/dashboard-plugins/rg-knowledge/dashboard/manifest.json", r'"version":\s*"([^"]+)"'),
    ("profiles/remedigenius/dashboard-plugins/rg-github/dashboard/manifest.json", r'"version":\s*"([^"]+)"'),
    ("profiles/remedigenius/dashboard-plugins/rg-board/dashboard/manifest.json", r'"version":\s*"([^"]+)"'),
)


def test_every_declared_version_is_the_package_version():
    """A release bumps one number; a profile manifest left behind makes Hermes report the old plugin version."""
    import re

    from rgtriage import __version__

    found = {}
    for name, pattern in VERSION_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        match = re.search(pattern, text, re.M)
        assert match, f"{name} declares no version"
        found[name] = match.group(1)
    assert set(found.values()) == {__version__}, found


def test_the_release_gate_asserts_the_baked_boot_path():
    """A boot that silently falls back to downloading would pass every other check and lose the reason for the image."""
    checks = (ROOT / "tools/spot_release_test.py").read_text(encoding="utf-8")
    assert "baked image: release archive already verified" in checks


def test_a_crlf_working_copy_cannot_change_a_release_archive(tmp_path, monkeypatch):
    """The v0.6.0 image was baked from an archive a Windows checkout had rewritten with CRLF."""
    import subprocess

    spec = importlib.util.spec_from_file_location("package_release_tool", ROOT / "tools/package_release.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.yaml").write_bytes(b"version: 1\nname: x\n")
    for command in (["git", "init", "-q"], ["git", "add", "a.yaml"],
                    ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "one"]):
        subprocess.run(command, cwd=repo, check=True)
    (repo / "a.yaml").write_bytes(b"version: 1\r\nname: x\r\n")  # the working copy diverges after the commit
    monkeypatch.setattr(tool, "ROOT", repo)
    assert tool.committed_bytes(repo / "a.yaml") == b"version: 1\nname: x\n"
    unstaged = repo / "b.yaml"
    unstaged.write_bytes(b"x\n")
    with pytest.raises(SystemExit, match="not in the git index"):
        tool.committed_bytes(unstaged)


# ------------------------------------------------------------------ the split

def test_durable_infrastructure_is_its_own_root_without_compute():
    static = read("aws-static", "main.tf")
    for owned in ('resource "aws_s3_bucket" "data"', 'resource "aws_glue_catalog_database" "ce"',
                  'resource "aws_iam_role" "host"', 'resource "aws_iam_role" "audit"',
                  'resource "aws_iam_instance_profile" "host"'):
        assert owned in static
    for compute in ("aws_launch_template", "aws_autoscaling_group", "aws_security_group"):
        assert compute not in static, f"{compute} belongs to the compute root"
    assert 'backend "s3"' in static and 'key = "aws-static/terraform.tfstate"' in static


def test_compute_root_only_creates_compute_and_reads_the_static_state():
    private = read("aws-private", "main.tf")
    assert 'resource "aws_launch_template" "host"' in private and 'resource "aws_autoscaling_group" "host"' in private
    assert 'data "terraform_remote_state" "static"' in private
    assert "aws_s3_bucket" not in private and "aws_glue_catalog_database" not in private
    assert "aws_iam_role" not in private  # roles live with the bucket they protect
    assert 'backend "s3"' in private and 'key = "aws-private/terraform.tfstate"' in private
    assert "var.running ? 1 : 0" in private  # parking keeps the data and the IAM


def test_compute_root_refuses_to_start_without_a_baked_image():
    private = read("aws-private", "main.tf")
    assert 'variable "ami_id"' in private and "ami-[0-9a-f]{8,}" in private
    assert "image_id      = var.ami_id" in private  # no silent fallback to a plain AMI on the maintainer's stack


def test_the_community_stack_still_works_without_an_image_and_uses_one_when_given(host):
    single = read("aws-single", "main.tf")
    assert 'variable "ami_id"' in single
    assert 'image_id      = var.ami_id == "" ? data.aws_ssm_parameter.ami.value : var.ami_id' in single
    # the community path keeps its own bucket, Glue database and roles: one apply, no state bucket to bootstrap
    assert 'resource "aws_s3_bucket" "data"' in single and 'resource "aws_autoscaling_group" "host"' in single


def test_every_root_declares_its_own_state_key_and_the_shared_backend_stays_a_template():
    for root, key in (("aws-static", "aws-static/terraform.tfstate"), ("aws-private", "aws-private/terraform.tfstate"),
                      ("ami", "aws-ami/terraform.tfstate")):
        text = read(root, "main.tf")
        assert 'backend "s3"' in text and f'key = "{key}"' in text
        assert "use_lockfile = true" in read("backend.hcl.example")
    template = read("backend.hcl.example")
    assert "<state-bucket-from-deploy-bootstrap>" in template
    assert not any(ch.isdigit() for ch in template.split("bucket")[1].splitlines()[0])


def test_bootstrap_creates_only_a_locked_down_state_bucket():
    text = read("bootstrap", "main.tf")
    assert 'resource "aws_s3_bucket" "state"' in text and "force_destroy = false" in text
    assert 'resource "aws_s3_bucket_versioning" "state"' in text
    assert "restrict_public_buckets = true" in text and "aws:SecureTransport" in text
    assert "output \"backend_hcl\"" in text and "use_lockfile = true" in text


def test_the_image_uses_the_release_as_its_semver_component_version():
    """Image Builder only accepts x.y.z for component and recipe versions, so the release string is used as-is."""
    ami = read("ami", "main.tf")
    assert "version  = var.release" in ami and "version      = var.release" in ami
    assert "replace(var.release" not in ami


def test_the_bootstrap_runs_on_the_base_image_python():
    """AL2023's `python3` is 3.9; host.py must parse there, not only on the 3.12 workstation."""
    import ast
    ast.parse(read("aws-single", "host.py"), feature_version=(3, 9))


# ------------------------------------------------------------------ the baked image

def test_the_image_bakes_the_runtime_and_the_pinned_hermes_image():
    ami = read("ami", "main.tf")
    assert "aws_imagebuilder_component" in ami and "aws_imagebuilder_image" in ami
    assert "host.py --bake --image" in ami and "--version" in ami
    assert "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b" in ami
    assert "amazon-linux-2023-x86/x.x.x" in ami and "amazon-linux-2023-arm64/x.x.x" in ami
    assert "sha256sum -c -" in ami  # the archive baked is the archive the stack will verify at boot
    # the build instance may read exactly the one archive
    assert 's3:GetObject"], Resource = "${data.terraform_remote_state.static.outputs.bucket_arn}/${local.archive_key}"' in ami


def test_first_boot_skips_the_download_when_the_image_already_has_the_verified_archive():
    user_data = read("aws-single", "user-data.sh.tftpl")
    assert "Path('/opt/rgtriage/.baked')" in user_data and "matches(archive)" in user_data
    assert "Source archive SHA-256 mismatch" in user_data
    assert "z.extractall(extract)" in user_data
    assert "'..' in path.parts" in user_data and "0o120000" in user_data  # traversal and symlink checks stay
    assert "command -v docker >/dev/null || dnf install" in user_data  # no package work on a baked image


def test_bake_writes_a_marker_the_boot_can_read(host, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(host, "ROOT", tmp_path)
    monkeypatch.setattr(host, "BAKED", tmp_path / ".baked")
    monkeypatch.setattr(host, "install_runtime", lambda: calls.append("runtime"))
    monkeypatch.setattr(host, "run", lambda *a, **k: calls.append(" ".join(a)))
    (tmp_path / "source.zip").write_bytes(b"zip")
    host.bake("nousresearch/hermes-agent@sha256:abc", "0.6.0")
    marker = json.loads((tmp_path / ".baked").read_text())
    assert marker["version"] == "0.6.0" and marker["image"].endswith("@sha256:abc")
    assert marker["packages"] == host.PACKAGES
    assert marker["source_sha256"] == __import__("hashlib").sha256(b"zip").hexdigest()
    assert "docker pull nousresearch/hermes-agent@sha256:abc" in calls and "runtime" in calls


def test_a_baked_image_skips_the_wheel_install_unless_this_release_pins_different_ones(host, tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    monkeypatch.setattr(host, "VENV", venv)
    monkeypatch.setattr(host, "CODE", tmp_path / "src")
    monkeypatch.setattr(host, "SOURCE", ROOT)
    monkeypatch.setattr(host, "ensure_user", lambda: None)
    monkeypatch.setattr(host, "install_wrapper", lambda: None)
    monkeypatch.setattr(host, "install_zip_binary", lambda *a: None)
    calls = []
    monkeypatch.setattr(host, "run", lambda *a, **k: calls.append(" ".join(a)))
    baked = tmp_path / "marker.json"
    monkeypatch.setattr(host, "BAKED", baked)

    baked.write_text(json.dumps({"packages": host.PACKAGES}))
    host.install_runtime()
    assert not [c for c in calls if "pip" in c], calls

    baked.write_text(json.dumps({"packages": ["something-old"]}))
    host.install_runtime()
    assert [c for c in calls if "pip" in c]  # a release with new pins still installs them on an older image


def test_booting_an_image_baked_for_another_digest_stops_instead_of_mixing_them(host, tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"image": "wanted@sha256:new"}))
    monkeypatch.setattr(host, "ROOT", tmp_path)
    monkeypatch.setattr(host, "baked_marker", lambda: {"image": "baked@sha256:old"})
    monkeypatch.setattr(host, "install_runtime", lambda: pytest.fail("the boot must stop before installing"))
    with pytest.raises(SystemExit, match="bake a new image"):
        host.main()


# ------------------------------------------------------------------ parking

def test_spot_cycle_can_start_park_and_report(monkeypatch):
    spec = importlib.util.spec_from_file_location("spot_cycle", ROOT / "tools/spot_cycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.STACK.parts[-2:]) == {"deploy", "aws-private"}
    assert module.mask("account 123456789012 leaked") == "account **************** leaked"
    source = (ROOT / "tools/spot_cycle.py").read_text(encoding="utf-8")
    assert 'choices=["up", "down", "status"]' in source
    assert "-var=running={'true' if running else 'false'}" in source
    # Terraform lets the last assignment win. `-var-file` must come first, or a settings file's
    # "running": true would override the flag and `down` would start an instance.
    assert source.index('f"-var-file={path}"') < source.index("-var=running=")
    assert "use_lockfile=true" in source
    assert "terraform" in source and "describe-auto-scaling-groups" in source
    # Terraform resolves -var-file inside the module directory; a relative path failed on the first real run.
    assert 'Path(settings.pop("_vars_file")).resolve()' in source