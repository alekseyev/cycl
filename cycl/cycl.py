from pathlib import Path
from typing import Dict, Optional

import plumbum.cmd
import typer
import yaml
from pydantic import BaseModel


class Server(BaseModel):
    host: str


class Globals(BaseModel):
    config_path = typer.get_app_dir("cycl")
    servers: Dict[str, Server] = {}


conf = Globals()
app = typer.Typer()


def load_servers() -> None:
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


@app.command()
def showremote():
    typer.echo(plumbum.cmd.git("config", "--get", "remote.origin.url"))


@app.command()
def list_servers():
    for name, server in conf.servers.items():
        typer.echo(f"{name}: {server.host}")


@app.callback()
def main(config_path: Optional[str] = None):
    if config_path:
        conf.config_path = config_path
    load_servers()


if __name__ == "__main__":
    app()
