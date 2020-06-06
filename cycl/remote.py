from plumbum import SshMachine
from plumbum.machines.remote import RemoteCommand

from .models import Server


class SshRunner:
    _server: Server
    _chdir: str
    _root: bool

    cmd: SshMachine

    docker_compose: RemoteCommand
    git: RemoteCommand
    pip: RemoteCommand

    def __init__(self, server: Server, chdir="", root=False):
        self._server = server
        self._chdir = chdir
        self._root = root

    def __enter__(self):
        if self._root:
            username = "root"
        else:
            username = self._server.username
        self.cmd = SshMachine(self._server.host, user=username)
        if self._chdir:
            if self._chdir.startswith("/"):
                self.cmd.cwd.chdir(self._chdir)
            else:
                self.cmd.cwd.chdir(self.cmd.cwd / self._chdir)

        if not self._root:
            self.docker_compose = self.cmd["docker-compose"]
            self.git = self.cmd["git"]
            self.pip = self.cmd["pip"]

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cmd.close()
