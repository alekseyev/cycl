from pathlib import Path
from typing import Optional

import plumbum.cmd
import typer
import yaml
from plumbum import FG

from .models import AppDeploymentSettings, Globals, Server
from .remote import SshRunner

conf = Globals()
app = typer.Typer()


def load_settings() -> None:
    config_dir = Path(conf.config_path)
    if not config_dir.exists():
        typer.echo("Warning: configuration directory doesn't exist!")
        config_dir.mkdir()
        return
    config_file_path = config_dir / "config.yaml"
    if not config_file_path.exists():
        typer.echo("Warning: configuration file doesn't exist!")
        return
    with config_file_path.open("r") as config_file:
        config = yaml.safe_load(config_file)
        conf.servers = {
            name: Server(**server) for name, server in config["servers"].items()
        }
    app_settings_path = Path.cwd() / "cycl.yaml"
    if not app_settings_path.exists():
        typer.echo("Warning: app deployment settings not found")
        return
    with app_settings_path.open("r") as app_settings_file:
        app_settings = yaml.safe_load(app_settings_file)
        conf.app = AppDeploymentSettings(**app_settings["deploy"])


@app.command()
def showremote():
    typer.echo(plumbum.cmd.git("config", "--get", "remote.origin.url"))


@app.command()
def list_servers():
    for name, server in conf.servers.items():
        typer.echo(f"{name}: {server.host}")


@app.command()
def remote_logs():
    """
    Show logs for remote docker-compose
    """
    with SshRunner(conf) as ssh:
        ssh.docker_compose["-f", conf.app.compose_file, "logs", "-f", "--tail=100"] & FG


@app.command()
def deploy_update():
    """
    Update remote deployment, restarts only servers in deploy.servers
    """
    with SshRunner(conf) as ssh:
        ssh.git["checkout", "."] & FG
        ssh.git["pull"] & FG
        ssh.git["checkout", conf.app.branch] & FG
        ssh.git["pull"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "build"] & FG
        ssh.docker_compose[
            "-f", conf.app.compose_file, "stop", conf.app.restart_services
        ] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "up", "-d"] & FG


@app.command()
def full_update():
    """
    Update remote deployment, rebuilds with --no-cache, restarts ALL servers
    """
    with SshRunner(conf) as ssh:
        ssh.git["checkout", "."] & FG
        ssh.git["pull"] & FG
        ssh.git["checkout", conf.app.branch] & FG
        ssh.git["pull"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "build", "--no-cache"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "down"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "up", "-d"] & FG


@app.callback()
def main(config_path: Optional[str] = None):
    if config_path:
        conf.config_path = config_path
    load_settings()


if __name__ == "__main__":
    app()
