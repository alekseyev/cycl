from collections import defaultdict
from pathlib import Path
from typing import Optional

import plumbum
import typer
import yaml
from plumbum import FG

from .models import Globals, ProjectSettings, Server, UtilityData
from .remote import SshRunner
from .utils import gen_password

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
    if not conf.proj_config.exists():
        typer.echo(f"Warning: project settings {conf.proj_config} not found")
        return
    with conf.proj_config.open("r") as proj_settings_file:
        proj_settings = yaml.safe_load(proj_settings_file)
        conf.proj = ProjectSettings(**proj_settings)
    cycl_dir = conf.project_dir / ".cycl"
    if not cycl_dir.exists():
        cycl_dir.mkdir()


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


@app.command()
def config():
    """
    Enact config changes: generate containers, initialize databases
    """
    compose_path = conf.proj_config.parent / ".cycl" / "docker-compose.yml"
    utils_path = conf.proj_config.parent / ".cycl" / "utils.yml"
    env_path = conf.proj_config.parent / ".cycl" / "cycl.env"

    utils_data = defaultdict(UtilityData)

    if utils_path.exists():
        with utils_path.open("r") as utils_file:
            utils_yaml = yaml.safe_load(utils_file)
            utils_data.update(
                {name: UtilityData(**data) for name, data in utils_yaml.items()}
            )

    services = {}
    env = {}
    utilities = []

    for name, utility in conf.proj.utilities.items():
        # TODO: picking any free port, grouping dbs
        utilities.append(name)
        if utility.type == "redis":
            services[name] = {
                "image": "redis",
                "ports": ["6379:6379"],
            }
            env[f"{name}_url"] = f"redis://{name}/1"
            env[f"{name}_host"] = name
            env[f"{name}_port"] = "6379"
            env[f"{name}_db"] = "1"

        if utility.type == "mongo":
            if utils_data[name].password:
                password = utils_data[name].password
            else:
                password = gen_password()
                utils_data[name] = UtilityData(password=password)
            services[name] = {
                "image": "mongo",
                "environment": {
                    "MONGO_INITDB_ROOT_USERNAME": "root",
                    "MONGO_INITDB_ROOT_PASSWORD": password,
                },
            }
            env[f"{name}_url"] = f"mongodb://{name}/"
            env[f"{name}_host"] = name
            env[f"{name}_port"] = "27017"
            env[f"{name}_db"] = name
            env[f"{name}_user"] = "root"
            env[f"{name}_password"] = password

    for name, worker in conf.proj.workers.items():
        worker_config = {  # image?
            "build": {"context": "./", "dockerfile": f"Dockerfile-{worker.type}"},
            "env_file": [".cycl/cycl.env"],
            "volumes": [".:/opt/worker"],
            "depends_on": utilities,
        }
        if worker.port:
            worker_config["ports"] = [f"{worker.port}:{worker.port}"]
        if worker.type == "python-web-fastapi":
            worker_config[
                "command"
            ] = f"uvicorn --host 0.0.0.0 --port {worker.port} {worker.entrypoint} --reload"
        services[name] = worker_config

    compose_yaml = {
        "version": "3.5",
        "services": services,
    }

    with compose_path.open("w") as compose_file:
        yaml.dump(compose_yaml, compose_file)

    if utils_data:
        utils_yaml = {name: util.dict() for name, util in utils_data.items()}
        with utils_path.open("w") as utils_file:
            yaml.dump(utils_yaml, utils_file)

    if env:
        with env_path.open("w") as env_file:
            for name, val in env.items():
                env_file.write(f"{name}={val}\n")


@app.callback()
def main(
    config_dir: Optional[str] = None, project_dir: Optional[str] = None,
):
    if config_dir:
        conf.config_dir = Path(config_dir)
    if project_dir:
        conf.project_dir = Path(project_dir)
        conf.proj_config = conf.project_dir / "cycl.yaml"
    load_settings()


if __name__ == "__main__":
    app()
