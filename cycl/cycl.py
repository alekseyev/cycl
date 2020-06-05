from pathlib import Path
from typing import Dict, List, Optional

import plumbum.cmd
import typer
import yaml
from plumbum import FG, SshMachine
from pydantic import BaseModel


class AppDeploymentSettings(BaseModel):
    server = "server"
    directory = "example"
    restart_services: List[str] = []
    compose_file = "docker-compose-deploy.yml"
    app_host = "example.com"
    app_port = 12345
    branch = "master"


class Server(BaseModel):
    host: str


class Globals(BaseModel):
    config_path = typer.get_app_dir("cycl")
    servers: Dict[str, Server] = {}
    app = AppDeploymentSettings()


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


def get_ssh() -> SshMachine:
    server = conf.servers[conf.app.server]
    return SshMachine(server.host)


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
    with get_ssh() as ssh:
        with ssh.cwd(ssh.cwd / conf.app.directory):
            docker_compose = ssh["docker-compose"]
            docker_compose["-f", conf.app.compose_file, "logs", "-f", "--tail=100"] & FG


@app.command()
def deploy_update():
    """
    Update remote deployment, restarts only servers in deploy.servers
    """
    with get_ssh() as ssh:
        with ssh.cwd(ssh.cwd / conf.app.directory):
            git = ssh["git"]
            docker_compose = ssh["docker-compose"]
            git["checkout", "."] & FG
            git["pull"] & FG
            git["checkout", conf.app.branch] & FG
            git["pull"] & FG
            docker_compose["-f", conf.app.compose_file, "build"] & FG
            docker_compose[
                "-f", conf.app.compose_file, "stop", conf.app.restart_services
            ] & FG
            docker_compose["-f", conf.app.compose_file, "up", "-d"] & FG


@app.command()
def full_update():
    """
    Update remote deployment, rebuilds with --no-cache, restarts ALL servers
    """
    with get_ssh() as ssh:
        with ssh.cwd(ssh.cwd / conf.app.directory):
            git = ssh["git"]
            docker_compose = ssh["docker-compose"]
            git["checkout", "."] & FG
            git["checkout", conf.app.branch] & FG
            git["pull"] & FG
            docker_compose["-f", conf.app.compose_file, "build", "--no-cache"] & FG
            docker_compose["-f", conf.app.compose_file, "down"] & FG
            docker_compose["-f", conf.app.compose_file, "up", "-d"] & FG


@app.callback()
def main(config_path: Optional[str] = None):
    if config_path:
        conf.config_path = config_path
    load_settings()


if __name__ == "__main__":
    app()
