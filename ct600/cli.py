import os
import sys
import click
import yaml
from ct600.build import build_xml
from ct600.submit import submit


def _load_env() -> None:
    """Load .env from the project root if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def _apply_env_credentials(data: dict) -> dict:
    """Override YAML credentials with env vars if set."""
    creds = dict(data.get("credentials", {}))
    if os.environ.get("HMRC_SENDER_ID"):
        creds["sender_id"] = os.environ["HMRC_SENDER_ID"]
    if os.environ.get("HMRC_PASSWORD"):
        creds["password"] = os.environ["HMRC_PASSWORD"]
    if os.environ.get("HMRC_VENDOR_ID"):
        creds["vendor_id"] = os.environ["HMRC_VENDOR_ID"]
    return {**data, "credentials": creds}


@click.command()
@click.argument("yaml_file", default="return.yaml")
@click.option("--lts", "target", flag_value="lts", default=True, help="Submit to local LTS (default)")
@click.option("--til", "target", flag_value="til", help="Submit to HMRC Test-in-Live")
@click.option("--live", "target", flag_value="live", help="Submit to HMRC production")
@click.option("--dry-run", is_flag=True, help="Build XML but do not submit")
@click.option("--output", "-o", type=click.Path(), help="Write generated XML to file")
def main(yaml_file: str, target: str, dry_run: bool, output: str | None) -> None:
    """Submit a CT600 corporation tax return to HMRC.

    YAML_FILE defaults to return.yaml in the current directory.
    Credentials can be set via HMRC_SENDER_ID, HMRC_PASSWORD, HMRC_VENDOR_ID
    environment variables (or a .env file) instead of in the YAML.
    """
    _load_env()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    data = _apply_env_credentials(data)

    gateway_test = target == "lts"
    xml = build_xml(data, gateway_test=gateway_test, til=(target == "til"))

    if output:
        with open(output, "wb") as f:
            f.write(xml)
        click.echo(f"XML written to {output}")

    if dry_run:
        click.echo("Dry run: XML built successfully, not submitted.")
        if not output:
            sys.stdout.buffer.write(xml)
        return

    if target == "live":
        click.confirm(
            "WARNING: This will submit a real CT600 to HMRC production. Continue?",
            abort=True,
        )

    click.echo(f"Submitting to {target}...")
    response = submit(xml, target=target)
    click.echo(response)
