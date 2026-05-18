"""LTS (Local Test Service) manager — install artefacts, start, stop, check status."""
import io
import os
import signal
import socket
import subprocess
import time
import zipfile
from pathlib import Path

import click
import requests
from lxml import etree

FEED_URL = "https://www.tpvs.hmrc.gov.uk/tools/v2/services.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
LTS_PORT = 5665
LTS_INFO_URL = "https://www.gov.uk/government/publications/local-test-service-and-lts-update-manager"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).parent.parent


def _lts_dir() -> Path:
    candidates = sorted(_project_root().glob("lts/LTS*/HMRCTools/LTS"))
    if not candidates:
        raise click.ClickException(
            "LTS directory not found. Run 'pdm run lts download' to fetch it."
        )
    return candidates[-1]


def _rim_dir() -> Path:
    # HMRCTools/RIMArtefacts — sibling of the LTS directory
    return _lts_dir().parent / "RIMArtefacts"


def _validator_config() -> Path:
    return _lts_dir() / "resources" / "config" / "NonConfigurable" / "validatorConfig.xml"


def _pid_file() -> Path:
    return _project_root() / ".lts.pid"


def _is_running() -> bool:
    try:
        with socket.create_connection(("localhost", LTS_PORT), timeout=2):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def lts() -> None:
    """Manage the HMRC Local Test Service."""


@lts.command()
def status() -> None:
    """Check whether the LTS is running."""
    if _is_running():
        click.echo(f"LTS is running on port {LTS_PORT}.")
    else:
        click.echo(f"LTS is not running (nothing on port {LTS_PORT}).")


@lts.command()
def start() -> None:
    """Start the LTS in the background."""
    if _is_running():
        click.echo("LTS is already running.")
        return

    lts_dir = _lts_dir()
    log_path = lts_dir / "logs" / "lts-stdout.log"
    log_path.parent.mkdir(exist_ok=True)

    env = {**os.environ, "LTS_HOME": str(lts_dir)}

    proc = subprocess.Popen(
        ["sh", "RunLTSStandalone.sh"],
        cwd=str(lts_dir),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_path.open("wb"),
        stderr=subprocess.STDOUT,
        start_new_session=True,  # own process group so stop() can kill java too
    )
    _pid_file().write_text(str(proc.pid))

    click.echo("Starting LTS", nl=False)
    for _ in range(60):  # up to 30s — JVM startup can take ~10s
        time.sleep(0.5)
        click.echo(".", nl=False)
        if _is_running():
            click.echo(f" ready. (log: {log_path.relative_to(_project_root())})")
            return
    click.echo(f" timed out. Check {log_path.relative_to(_project_root())}")


@lts.command()
def stop() -> None:
    """Stop a running LTS."""
    pid_file = _pid_file()
    if not pid_file.exists():
        click.echo("No PID file found — was the LTS started with 'lts start'?")
        return
    pid = int(pid_file.read_text().strip())
    try:
        os.killpg(pid, signal.SIGTERM)
        click.echo(f"Sent SIGTERM to process group {pid}.")
    except ProcessLookupError:
        click.echo(f"Process group {pid} not found (already stopped?).")
    pid_file.unlink(missing_ok=True)


@lts.command()
@click.option("--force", is_flag=True, help="Re-download even if an LTS directory already exists.")
def download(force: bool) -> None:
    """Download and unzip the HMRC Local Test Service.

    Fetches the latest LTS zip from the HMRC feed and extracts it into the
    current directory. Only needs to be done once. See also:
    https://www.gov.uk/government/publications/local-test-service-and-lts-update-manager
    """
    existing = sorted(_project_root().glob("lts/LTS*/HMRCTools/LTS"))
    if existing and not force:
        click.echo(f"LTS already present at {existing[-1].parent.parent.relative_to(_project_root())}. Use --force to re-download.")
        return

    click.echo("Fetching HMRC services feed to find latest LTS version...")
    resp = requests.get(FEED_URL, timeout=30)
    resp.raise_for_status()
    feed = etree.fromstring(resp.content)

    url = None
    title = None
    for entry in feed.findall(f"{ATOM}entry"):
        cat = entry.find(f"{ATOM}category")
        if cat is not None and cat.get("term") == "Notification":
            link = entry.find(f"{ATOM}link[@type='application/zip']")
            if link is not None:
                url = link.get("href")
                title = entry.findtext(f"{ATOM}title") or url
                break

    if not url:
        raise click.ClickException("Could not find LTS download URL in HMRC feed.")

    click.echo(f"Downloading {title} from {url} ...")
    data = requests.get(url, timeout=120, stream=True)
    data.raise_for_status()

    raw = b"".join(data.iter_content(chunk_size=65536))
    click.echo(f"Downloaded {len(raw) / 1_048_576:.1f} MB. Extracting...")

    dest = _project_root() / "lts"
    dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        # Extract only HMRCTools/ entries, skipping __MACOSX metadata
        members = [m for m in zf.namelist() if not m.startswith("__MACOSX")]
        for name in members:
            target = dest / name
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))

    lts_dirs = sorted(dest.glob("*/HMRCTools/LTS"))
    if lts_dirs:
        click.echo(f"Done. LTS extracted to {lts_dirs[-1].parent.parent.relative_to(dest)}/")
        click.echo("Next steps: pdm run lts install && pdm run lts start")
    else:
        click.echo("Extraction complete (LTS directory structure may differ — check manually).")


@lts.command()
@click.option("--service", default="CT", show_default=True, help="Feed category prefix to filter.")
@click.option("--force", is_flag=True, help="Re-download and re-install even if already present.")
def install(service: str, force: bool) -> None:
    """Download and install RIM artefacts from the HMRC feed."""
    click.echo("Fetching HMRC services feed...")
    resp = requests.get(FEED_URL, timeout=30)
    resp.raise_for_status()

    feed = etree.fromstring(resp.content)
    entries = _parse_feed_entries(feed, service)

    if not entries:
        raise click.ClickException(f"No '{service}' artefacts found in HMRC feed.")

    # Most-recently updated package first
    entries.sort(key=lambda e: e["updated"], reverse=True)
    latest = entries[0]
    click.echo(
        f"Found {len(entries)} '{service}' package(s). "
        f"Using: {latest['title']} (updated {latest['updated'][:10]})"
    )

    dest_dir = _rim_dir() / latest["term"]
    if dest_dir.exists() and not force:
        click.echo(f"Already installed at {dest_dir.relative_to(_project_root())}. Use --force to reinstall.")
    else:
        _download_and_extract(latest, dest_dir)

    _register_in_validator_config(latest["term"], dest_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_feed_entries(feed: etree._Element, service_prefix: str) -> list[dict]:
    entries = []
    for entry in feed.findall(f"{ATOM}entry"):
        cat = entry.find(f"{ATOM}category")
        if cat is None:
            continue
        term = cat.get("term", "")
        if not term.startswith(service_prefix + "/"):
            continue
        link = entry.find(f"{ATOM}link[@type='application/zip']")
        if link is None:
            continue
        entries.append({
            "term": term,
            "title": entry.findtext(f"{ATOM}title") or term,
            "url": link.get("href"),
            "updated": entry.findtext(f"{ATOM}updated") or "",
            "content": entry.findtext(f"{ATOM}content") or "",
        })
    return entries


def _parse_content_directive(content: str) -> dict[str, str]:
    """Parse lines like 'Calc.jar:LTS/lib' into {filename: install_path}."""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in (":", "="):
            if sep in line:
                fname, path = line.split(sep, 1)
                result[fname.strip()] = path.strip()
                break
    return result


def _download_and_extract(entry: dict, dest_dir: Path) -> None:
    click.echo(f"Downloading {entry['url']} ...")
    resp = requests.get(entry["url"], timeout=60)
    resp.raise_for_status()

    # Files listed in content go to a custom path under HMRCTools/;
    # everything else goes to the RIMArtefacts destination directory.
    custom = _parse_content_directive(entry["content"])
    hmrc_tools = _lts_dir().parent  # HMRCTools/

    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if name in custom:
                target = hmrc_tools / custom[name] / name
            else:
                target = dest_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            click.echo(f"  {target.relative_to(_project_root())}")


def _register_in_validator_config(term: str, artefacts_dir: Path) -> None:
    """Add a <Service> entry to validatorConfig.xml if not already present."""
    service_cfg = artefacts_dir / "serviceConfig.xml"
    if not service_cfg.exists():
        click.echo("  Warning: no serviceConfig.xml found; skipping validatorConfig.xml update.")
        return

    sc_root = etree.parse(str(service_cfg)).getroot()
    svc_el = sc_root.find("Service")
    if svc_el is None:
        click.echo("  Warning: no <Service> in serviceConfig.xml; skipping validatorConfig.xml update.")
        return
    namespace_uri = svc_el.get("uri")

    cfg_path = _validator_config()
    tree = etree.parse(str(cfg_path))
    cfg_root = tree.getroot()

    envelope_el = cfg_root.find("Envelope")
    if envelope_el is None:
        raise click.ClickException("No <Envelope> element found in validatorConfig.xml.")

    for existing in envelope_el.findall("Service"):
        if existing.get("uri") == namespace_uri:
            click.echo(f"  {namespace_uri!r} already registered in validatorConfig.xml.")
            return

    new_svc = etree.SubElement(envelope_el, "Service", uri=namespace_uri)
    etree.SubElement(new_svc, "TotalErrorCap").text = "100"
    etree.SubElement(new_svc, "ValidationType").text = "COMPLETE"
    etree.SubElement(new_svc, "RIMArtefactsDirectory").text = term

    tree.write(str(cfg_path), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    click.echo(f"  Registered {namespace_uri!r} → {term} in validatorConfig.xml.")
