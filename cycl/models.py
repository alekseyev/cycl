from pathlib import Path
from typing import Dict, List

import typer
from pydantic import BaseModel


class WorkerSettings(BaseModel):
    port: int = None
    type: str
    entrypoint: str


class UtilitySettings(BaseModel):
    type: str


class ProjectSettings(BaseModel):
    workers: Dict[str, WorkerSettings] = {}
    utilities: Dict[str, UtilitySettings] = {}


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
    username = "cycl"


class Globals(BaseModel):
    config_dir = Path(typer.get_app_dir("cycl"))
    project_dir = Path.cwd()
    proj_config = Path.cwd() / "cycl.yaml"
    servers: Dict[str, Server] = {}
    proj = ProjectSettings()


class UtilityData(BaseModel):
    password: str = None
