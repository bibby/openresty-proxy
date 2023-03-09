import os

from jinja2 import Environment

from . import CONF_DIR


def list_custom_confs(service_fqdn):
    custom_path = "/".join([CONF_DIR, service_fqdn])
    custom_confs = []
    if os.path.isdir(custom_path):
        custom_confs = sorted(
            [
                open(os.path.join(dirpath, f), "r").read()
                for dirpath, _dirnames, files in os.walk(custom_path)
                for f in files
            ]
        )
    return custom_confs


class Service:
    def __init__(self, service_fqdn, upstream):
        self.containers = []
        self.fqdn = service_fqdn
        self.upstream = upstream
        self.default_server = False
        self.serve_http = False
        self.proxy_pass = False
        self.custom_confs = list_custom_confs(service_fqdn)
        # omit the default "location /" block  (label: openresty.skip_root_location=True)
        self.skip_root_location = False
        # run custom confs through jinja2  (label: openresty.render_confs=True)
        self.render_confs = False
        self.auth_basic_file = None
        self.auth_cert_bundle = None
        self.required_group = None
        self.max_upload_size = "20M"

    def add_container(self, container):
        copy_keys = [
            "default_server",
            "proxy_pass",
            "skip_root_location",
            "render_confs",
            "auth_basic_file",
            "auth_cert_bundle",
            "required_group",
            "max_upload_size",
            "serve_http",
        ]

        for k in copy_keys:
            val = getattr(container, k, None)
            if val:
                setattr(self, k, val)
        self.containers.append(container)

    @staticmethod
    def set_latest(service):
        latest_date = None
        for container in service.containers:
            d = container.created_date()
            if latest_date is None or d > latest_date:
                latest_date = d

        for container in service.containers:
            if container.created_date() != latest_date:
                container.options = "backup"

        return service

    def server_names(self):
        names = {self.fqdn}
        for container in self.containers:
            if container.nginx_use_other_names and container.other_names:
                names = names.union(set(container.other_names))
        return " ".join(names)

    @property
    def cert_name(self):
        for container in self.containers:
            if container.cert_name:
                return container.cert_name
        for container in self.containers:
            if container.service_fqdn:
                return container.service_fqdn

    @property
    def rendered_custom_confs(self):
        return [
            Environment().from_string(conf).render(service=self)
            for conf in self.custom_confs
        ]
