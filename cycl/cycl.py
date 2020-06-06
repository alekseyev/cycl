from pathlib import Path
from typing import Optional

import plumbum
import typer
import yaml
from plumbum import FG

from .models import AppDeploymentSettings, Globals, Server
from .remote import SshRunner

conf = Globals()
app = typer.Typer()


def load_settings() -> None:
    if not conf.config_dir.exists():
        typer.echo("Warning: configuration directory doesn't exist!")
        conf.config_dir.mkdir()
        return
    config_file_path = conf.config_dir / "config.yaml"
    if not config_file_path.exists():
        typer.echo("Warning: configuration file doesn't exist!")
        return
    with config_file_path.open("r") as config_file:
        config = yaml.safe_load(config_file)
        conf.servers = {
            name: Server(**server) for name, server in config["servers"].items()
        }
    if not conf.app_config.exists():
        typer.echo(f"Warning: app deployment settings {conf.app_config} not found")
        return
    with conf.app_config.open("r") as app_settings_file:
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
def setup_server(server_name: str):
    """
    Setup remote server for future deployments
    """
    server = conf.servers[server_name]
    with SshRunner(server, root=True) as ssh:
        ssh.cmd["apt"][
            "install", "-y", "docker-ce", "docker-compose", "nginx", "python-pip"
        ] & FG
        try:
            ssh.cmd["id"]("-u", server.username)
        except plumbum.ProcessExecutionError:
            ssh.cmd["useradd"][
                "-m", "-s", "/bin/bash", "-G", "sudo,docker", server.username
            ] & FG
        if not ssh.cmd.path(f"/home/{server.username}/.ssh/authorized_keys").exists():
            ssh.cmd["rsync"][
                "--archive",
                f"--chown={server.username}:{server.username}",
                "/root/.ssh/authorized_keys",
                f"/home/{server.username}/.ssh",
            ] & FG
    with SshRunner(server) as ssh:
        ssh.pip["install", "poetry"] & FG
    with SshRunner(server) as ssh:
        if not ssh.cmd.path(f"/home/{server.username}/cycl/.git").exists():
            ssh.git["clone", "https://github.com/alekseyev/cycl.git"] & FG
        ssh.cmd.cwd.chdir(ssh.cmd.cwd / "cycl")
        ssh.git["pull"] & FG
        ssh.cmd["poetry"]["install", "--no-dev"] & FG


@app.command()
def remote_logs():
    """
    Show logs for remote docker-compose
    """
    server = conf.servers[conf.app.server]
    with SshRunner(server, conf.app.directory) as ssh:
        ssh.docker_compose["-f", conf.app.compose_file, "logs", "-f", "--tail=100"] & FG


@app.command()
def deploy_update():
    """
    Update remote deployment, restarts only servers in deploy.servers
    """
    server = conf.servers[conf.app.server]
    with SshRunner(server, conf.app.directory) as ssh:
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
    server = conf.servers[conf.app.server]
    with SshRunner(server, conf.app.directory) as ssh:
        ssh.git["checkout", "."] & FG
        ssh.git["pull"] & FG
        ssh.git["checkout", conf.app.branch] & FG
        ssh.git["pull"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "build", "--no-cache"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "down"] & FG
        ssh.docker_compose["-f", conf.app.compose_file, "up", "-d"] & FG


@app.callback()
def main(
    config_dir: Optional[str] = None,
    app_config_dir: Optional[str] = None,
    app_config: Optional[str] = None,
):
    if config_dir:
        conf.config_dir = Path(config_dir)
    if app_config:
        conf.app_config = Path(app_config)
    elif app_config_dir:
        conf.app_config = Path(app_config_dir) / "cycl.yaml"
    load_settings()


if __name__ == "__main__":
    app()
