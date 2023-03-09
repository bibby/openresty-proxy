import re

from dateutil.parser import parse as date_parse

from . import environ, logger

NGINX_OPTION_PREFIX = environ("NGINX_OPTION_PREFIX", "openresty")


class Container:
    local_domain = environ("LOCAL_DOMAIN", "bibby.local")

    def __init__(self, container, env=None):
        name = container.attrs.get("Name", "").lstrip("/")
        config = container.attrs.get("Config", {})
        env = env or Container.fmt_env(config.get("Env", []))
        labels = config.get("Labels", {})
        exposures = Container.fmt_exposure(config.get("ExposedPorts", {}))

        network_mode = container.attrs.get("HostConfig", {}).get(
            "NetworkMode", None
        )

        logger.info("%s network_mode: %s", name, network_mode)
        logger.debug(
            "%s hostinfo: %s ", name, str(container.attrs.get("HostConfig", {}))
        )

        if network_mode == "default":
            ip_address = container.attrs.get("NetworkSettings", {}).get(
                "IPAddress", None
            )
        else:
            ip_address = (
                container.attrs.get("NetworkSettings", {})
                .get("Networks", {})
                .get(network_mode, {})
                .get("IPAddress", None)
            )

        logger.info("%s ip_address: %s", name, ip_address)

        options = []
        for option in ("weight", "fail_timeout", "slow_start", "max_fails"):
            label = ".".join([NGINX_OPTION_PREFIX, "opt", option])
            if label in labels:
                options.append("=".join([option, labels[label]]))

        # precedence order
        service_fqdn = env.get("SERVICE_FQDN", None)
        domain_name = config.get("Domainname", None)
        virtual_host = env.get("VIRTUAL_HOST", None)
        service_name = env.get("SERVICE_NAME", None)

        secret_id = env.get("PKI_SECRET_ID", None)
        role_id = env.get("PKI_ROLE_ID", None)

        if not service_fqdn:
            if domain_name:
                service_fqdn = domain_name
            elif virtual_host:
                service_fqdn = virtual_host
            elif service_name:
                service_fqdn = ".".join(
                    map(str, [virtual_host, Container.local_domain])
                )

        pki_role = env.get("PKI_ROLE", service_fqdn)
        other_names = env.get("OTHER_DNS_NAMES", None)

        if other_names:
            other_names = set(
                [n.strip() for n in re.split("[, ]*", other_names) if n.strip()]
            )
            if service_fqdn in other_names:
                other_names.remove(service_fqdn)
            other_names = list(other_names)

        nginx_use_other_names = env.get("NGINX_USE_OTHER_NAMES", True)
        if isinstance(nginx_use_other_names, str) and \
                nginx_use_other_names.lower() in ("no", "false", "0"):
            nginx_use_other_names = False

        def get_env_opt(opt):
            opt_label = ".".join([NGINX_OPTION_PREFIX, opt])
            return labels.get(opt_label, None) or env.get(opt.upper(), None)

        label_env_opts = [
            "default_server",
            "cert_name",
            "serve_http",
            "proxy_pass",
            "skip_root_location",
            "render_confs",
            "auth_basic_file",
            "auth_cert_bundle",
            "required_group",
            "max_upload_size",
        ]

        label_opts = dict()
        for opt in label_env_opts:
            label_opts[opt] = get_env_opt(opt)

        self.container = container
        self.name = name
        self.env = env
        self.image = config.get("Image")
        self.labels = labels
        self.exposures = exposures
        self.service_fqdn = service_fqdn
        self.upstream = service_fqdn
        self.other_names = other_names
        self.nginx_use_other_names = nginx_use_other_names
        self.network = network_mode
        self.ip_address = ip_address
        self.default_server = label_opts["default_server"]
        self.options = " ".join(map(str, options))
        self.proxy_pass = label_opts["proxy_pass"]
        self.cert_name = label_opts["cert_name"]
        self.exposed_port = self.get_exposed_port()
        self.secret_id = secret_id
        self.role_id = role_id
        self.pki_role = pki_role
        self.serve_http = label_opts["serve_http"]
        self.skip_root_location = label_opts["skip_root_location"]
        self.render_confs = label_opts["render_confs"]
        self.auth_basic_file = label_opts["auth_basic_file"]
        self.auth_cert_bundle = label_opts["auth_cert_bundle"]
        self.required_group = label_opts["required_group"]
        self.max_upload_size = label_opts["max_upload_size"]

        logger.debug("? name = %s", name)
        logger.debug("? label_opts = %s", label_opts)

    def __getattr__(self, name):
        return getattr(self.container, name)

    @staticmethod
    def fmt_env(env_pairs):
        """["FOO=bar", "BAR=baz"]
        to {'FOO': 'bar', 'BAR': 'baz'}
        """
        env_map = {k: v for k, v in tuple(item.split("=", 1) for item in env_pairs)}
        logger.debug(env_map)
        return env_map

    def rotate_env(self, ns):
        ns = ns + "_"
        env = self.env

        important_keys = [
            "SERVICE_FQDN",
            "VIRTUAL_HOST",
            "VIRTUAL_PORT",
            "CERT_NAME",
            "OTHER_DNS_NAMES",
            "PKI_ROLE",
            "PKI_SECRET_ID",
        ]

        for k in important_keys:
            if k in env:
                del env[k]

        for k in env.keys():
            if not k.startswith(ns):
                continue

            logger.debug("%s <- %s", k[len(ns):], k)
            env[k[len(ns):]] = env[k]
        return env

    def copy(self, env=None):
        return Container(self.container, env)

    @staticmethod
    def fmt_exposure(exposures):
        return [ex.split("/", 1)[0] for ex in exposures]

    def get_exposed_port(self):
        # custom port
        custom = self.env.get("VIRTUAL_PORT", None)
        if custom:
            return custom

        # freestyle container
        exposed = self.exposures
        if len(exposed) == 0:
            return 0
        return exposed[0]

    def created_date(self):
        image_date = self.labels.get("org.label-schema.build-date", None)
        created_date = self.attrs.get("Created", None)
        return date_parse(image_date or created_date)
