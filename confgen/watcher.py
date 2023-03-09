import json
import os
import signal
import subprocess
import threading

import docker

from gen import ConfGen
from . import environ, logger


class Watcher:
    def __init__(self, vault_addr=None, vault_pki=None):
        self.timer = None
        self.client = docker.DockerClient(
            base_url="unix://var/run/docker.sock",
            version=environ("DOCKER_API_VERSION", None),
        )
        self.generator = ConfGen()

    def begin_watch(self):
        self.trigger_rebuild()
        for event in self.client.events():
            event = json.loads(event)
            self.handle_event(event)

    def handle_event(self, event):
        status = event.get("status")
        logger.debug(
            [status, event.get("Actor", {}).get("Attributes", {}).get("name", "")]
        )
        if status in ("start", "stop", "kill", "die"):
            logger.debug(
                "timer = %s, status = %s"
                % (self.timer is not None, event.get("status"))
            )
            self.trigger_rebuild()

    def trigger_rebuild(self):
        if not self.timer:
            logger.debug("timer start")
            self.timer = threading.Timer(ConfGen.DEFER_TIME, self.generate_config)
            self.timer.start()

    def generate_config(self, force=None):
        logger.debug("generate config")
        self.timer = None
        if self.generator.generate(self.client) or force:
            self.hup_frontend()

    def hup_frontend(self):
        logger.info("Cycle frontend")
        try:
            cmd = "ps -ef | grep 'nginx: master' | grep -v grep | awk '{print $2}'"
            proc = subprocess.check_output(cmd, shell=True).strip()
            if not proc:
                raise ValueError("no nginx process")

            pid = int(proc)
            os.kill(pid, signal.SIGHUP)
            logger.info("Sent SIGHUP to pid %d" % (pid,))
            return True
        except Exception as e:
            logger.exception(e)
            raise
