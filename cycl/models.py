from typing import Dict, List

import typer
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
