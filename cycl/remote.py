from plumbum import SshMachine
from plumbum.machines.remote import RemoteCommand

from .models import Globals


class SshRunner:
    _conf: Globals
    _chdir: bool
    _ssh_machine: SshMachine

    docker_compose: RemoteCommand
    git: RemoteCommand

    def __init__(self, conf: Globals, chdir=True):
        self._conf = conf
        self._chdir = chdir

    def __enter__(self):
        server = self._conf.servers[self._conf.app.server]
        self._ssh_machine = SshMachine(server.host)
        if self._chdir:
            if self._conf.app.directory.startswith("/"):
                self._ssh_machine.cwd.chdir(self._conf.app.directory)
            else:
                self._ssh_machine.cwd.chdir(
                    self._ssh_machine.cwd / self._conf.app.directory
                )

        self.docker_compose = self._ssh_machine["docker-compose"]
        self.git = self._ssh_machine["git"]

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ssh_machine.close()
