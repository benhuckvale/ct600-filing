import sys
import click
import yaml
from ct600.build import build_xml
from ct600.submit import submit


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
    """
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    gateway_test = target != "live"
    xml = build_xml(data, gateway_test=gateway_test)

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
