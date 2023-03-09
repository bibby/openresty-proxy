import json
import os
from time import time

import requests
from jinja2 import Environment, PackageLoader, select_autoescape

from approle import login
from container import Container
from service import Service
from . import environ, truthy, logger, CONF_DIR, CERT_DIR

VTS_ENABLED = truthy(environ("VTS_ENABLED"))
VTS_PATH = environ("VTS_PATH")
VTS_USER_AGENT = truthy(environ("VTS_USER_AGENT"))
VTS_URIS = truthy(environ("VTS_URIS"))

GRAYLOG_ENABLED = truthy(environ("GRAYLOG_ENABLED"))
GRAYLOG_DOMAIN = environ("GRAYLOG_DOMAIN")
GRAYLOG_PORT_ACCESS = int(environ("GRAYLOG_PORT_ACCESS"))
GRAYLOG_PORT_ERROR = int(environ("GRAYLOG_PORT_ERROR"))

CA_EXPIRE = int(environ("CA_EXPIRE"))
CA_BUFFER_TIME = int(environ("CA_BUFFER_TIME", 3600 * 3))
SIX_MON = 15552000


def cert_file(domain, ext="crt"):
    return CERT_DIR + "/" + domain + "." + ext


def pretty_json(dict_obj):
    return json.dumps(dict_obj, sort_keys=True, indent=4, separators=(",", ": "))


class ConfGen:
    DEFER_TIME = 2
    INDENT = " " * 2
    burned = set()

    def __init__(self, **kwargs):
        self.certgen = CertGen(**kwargs)
        self.env = Environment(
            loader=PackageLoader("confgen", "templates"),
            autoescape=select_autoescape(["tpl"]),
        )

    @staticmethod
    def burn(secret):
        ConfGen.burned.add(secret)

    def generate(self, client):
        services = self.get_services(client)
        logger.info("services = %d" % (len(services),))
        template = self.env.get_template("conf.tpl")

        generate_config = True
        conf_file = CONF_DIR + "/default.conf"
        conf_content = template.render(
            services=services,
            opts=dict(
                VTS_ENABLED=VTS_ENABLED,
                VTS_PATH=VTS_PATH,
                VTS_URIS=VTS_URIS,
                VTS_USER_AGENT=VTS_USER_AGENT,
                OPENRESTY_LOG_LEVEL=environ("OPENRESTY_LOG_LEVEL", "warn"),
            ),
            graylog=dict(
                enabled=GRAYLOG_ENABLED,
                domain=GRAYLOG_DOMAIN,
                ports=dict(
                    access=GRAYLOG_PORT_ACCESS,
                    error=GRAYLOG_PORT_ERROR,
                ),
            ),
        )

        if os.path.isfile(conf_file):
            with open(conf_file, "r") as conf:
                prev_content = conf.read()
                if prev_content == conf_content:
                    generate_config = False

        if generate_config:
            with open(conf_file, "w") as conf:
                conf.write(ConfGen.tidy(str(conf_content)))

        return generate_config

    @staticmethod
    def tidy(contents):
        lines = map(str.strip, contents.splitlines())
        current_indent = 0
        tidy_lines = []
        for line in lines:
            if not len(line):
                continue

            if line.endswith("}"):
                tidy_lines.append("")
                current_indent -= 1

            if line.endswith("{"):
                tidy_lines.append("")

            tidy_lines.append(current_indent * ConfGen.INDENT + line)

            if line.endswith("{"):
                current_indent += 1

        return "\n".join(tidy_lines)

    def get_services(self, client):
        # something usable by the template
        services = {}
        default_container = None
        containers = map(Container, client.containers.list())
        # proxy_container = [c for c in containers if c.labels.get("openresty.proxy")]
        # if proxy_container:
        #   proxy_container = proxy_container[0]
        #   named_network = proxy_container.network

        for container in containers:
            # pretty_json(container.attrs)
            if container.default_server:
                if default_container:
                    msg = "%s default_server status removed, already set by %s"
                    logger.warn(msg % (container.name, default_container.name))
                    container.default_server = False
                else:
                    default_container = Container

            for cont in self.qualify_container(container):
                if cont.service_fqdn not in services:
                    services[cont.service_fqdn] = Service(
                        cont.service_fqdn, cont.upstream
                    )
                services[cont.service_fqdn].add_container(cont)

        return sorted(
            map(Service.set_latest, services.values()),
            key=lambda c: (c.fqdn != c.upstream, c.fqdn),
        )

    def qualify_container(self, container, force_regen=None):
        containers = []
        if not self.__qualify_container(container, force_regen=force_regen):
            return containers

        containers.append(container)
        for n in ["second", "third", "fourth", "fifth", "sixth"]:
            logger.debug("Attempting additional domain: %s", n)
            c = container.copy(container.rotate_env(n.upper()))
            if self.__qualify_container(c, force_regen=force_regen):
                logger.debug("%s domain is valid, adding", n)
                containers.append(c)
            else:
                logger.debug("%s domain invalid or missing. done here.", n)
                break

        return containers

    def __qualify_container(self, container, force_regen=None):
        qualified = (
                self.__qualify_container_cfg(container)
                and self.__qualify_container_auth(container)
                and self.__qualify_container_cert(container, force_regen=force_regen)
        )

        if qualified:
            logger.info("Adding service: %s" % (container.name,))
        return qualified

    @staticmethod
    def __qualify_container_cfg(container):
        if "NGINX_PROXY_IGNORE" in container.env:
            logger.info("%s ignored by own config." % (container.name,))
            return False

        if not container.service_fqdn:
            logger.info("%s did not qualify;  lack of service_fqdn" % (container.name,))
            return False

        if not container.exposures:
            logger.info("%s did not qualify;  lack of exposures" % (container.name,))
            return False

        if not container.exposed_port:
            logger.info(
                "%s did not qualify;  lack of definitive port exposure"
                % (container.name,)
            )
            return False

        if not container.ip_address:
            logger.info(
                "%s did not qualify;  has no ip_address; is there a named network?"
                % (container.name,)
            )
            return False

        if container.proxy_pass:
            logger.info("PROXY_PASS = " + container.service_fqdn)

        logger.info("cfg passes (1/3) " + container.service_fqdn)
        return True

    @staticmethod
    def __qualify_container_auth(container):
        logger.debug(
            "Auth Basic File: %s %s", container.service_fqdn, container.auth_basic_file
        )
        if container.auth_basic_file:
            if not os.path.isfile(container.auth_basic_file):
                msg = " ".join(
                    [
                        "container uses basic auth, but passwd file not found.",
                        "The openresty container needs this file; not the target container",
                    ]
                )
                logger.info(msg)
                return False

        logger.debug(
            "Auth Cert Bundle: %s %s",
            container.service_fqdn,
            container.auth_cert_bundle,
        )
        if container.auth_cert_bundle:
            if not os.path.isfile(container.auth_cert_bundle):
                msg = " ".join(
                    [
                        "container uses client-cert auth, but cert bundle not found.",
                        "The openresty container needs this file; not the target container",
                    ]
                )
                logger.info(msg)
                return False

        logger.info("auth passes (2/3) " + container.service_fqdn)
        return True

    def __qualify_container_cert(self, container, force_regen=None):
        if container.nginx_use_other_names:
            other_names = container.other_names
            include_short_domain = True
        else:
            logger.info("excluding short and other names for " + container.service_fqdn)
            other_names = []
            include_short_domain = False

        if not self.certgen.cert_exists(container):
            if not container.role_id:
                msg = "%s did not qualify;  missing role_id (this version requires one " \
                      "for approles) "
                logger.info(msg % (container.name,))
                return False

            if not container.secret_id:
                msg = "%s did not qualify;  missing secret_id (this version requires one " \
                      "for approles) "
                logger.info(msg % (container.name,))
                return False

            if container.secret_id in ConfGen.burned:
                msg = "%s did not qualify;  secret_id has been burned"
                logger.info(msg % (container.name,))
                return False

        cert = self.certgen.ensure_certificate(
            container,
            other_names,
            force=force_regen,
            include_short_domain=include_short_domain,
        )

        if not cert:
            msg = "%s did not qualify; error generating certificate"
            logger.warning(msg % (container.name,))
            return False

        logger.info("cert passes (3/3) " + container.service_fqdn)
        return True


class CertGen:
    KNOWN_ROOTS = [
        s.strip() for s in environ("KNOWN_ROOTS", "").split(",") if s.strip()
    ]

    secret_updates = dict()

    def __init__(self, vault_addr=None, vault_pki=None):
        self.vault_addr = vault_addr or environ("VAULT_ADDR")
        self.vault_pki = vault_pki or environ("VAULT_PKI")

    def sni_domains(self, domains):
        dns_names = set(domains)
        for domain in domains:
            for root in CertGen.KNOWN_ROOTS:
                if root in domain:
                    short = self.shorten_domain(domain, root)
                    if short:
                        dns_names.add(short)

        return list(dns_names)

    @staticmethod
    def shorten_domain(domain, root):
        domain_segments = [item.strip() for item in domain.split(".")]
        root_segments = [item.strip() for item in root.split(".")]
        while len(root_segments):
            seg = root_segments.pop()
            if domain_segments[-1] == seg:
                domain_segments.pop()

        if len(domain_segments):
            return ".".join(domain_segments)

    @staticmethod
    def cert_exists(container):
        domain = container.service_fqdn
        cert_name = container.cert_name or domain
        certificate = cert_file(cert_name)
        exists = os.path.isfile(certificate)
        logger.debug("cert_exists? %s %s", certificate, exists)
        return exists

    def ensure_certificate(
            self, container, other_names, force=False, include_short_domain=True
    ):
        domain = container.service_fqdn
        logger.debug("ensure_certificate: %s,  forced=%s", domain, force)
        cert_name = container.cert_name or domain
        if force or not self.cert_exists(container):
            try:
                return self.generate_certificate(
                    container,
                    other_names,
                    cert_name,
                    include_short_domain=include_short_domain,
                )
            except Exception as e:
                logger.exception(e)
                return False
        return True

    def generate_certificate(
            self, container, other_names, cert_name, include_short_domain=True
    ):
        domain = container.service_fqdn
        logger.info("generate_certificate: " + domain)
        role_id = container.role_id
        logger.debug("secret_updates: " + str(CertGen.secret_updates))
        secret_id = CertGen.secret_updates.get(domain, container.secret_id)
        logger.debug("secret_id: " + str(secret_id))

        domains = [domain]
        if other_names:
            domains += other_names

        logger.debug(["include_short_domain", include_short_domain])
        if include_short_domain:
            domains = self.sni_domains(domains)

        logger.debug(["Generating", [cert_name + ".crt", domains]])
        ConfGen.burn(secret_id)
        vault_token = login(role_id, secret_id)
        if not vault_token:
            return False

        ttl = min(
            SIX_MON,
            CA_EXPIRE - int(time()) - CA_BUFFER_TIME,
        )

        logger.debug("CA_EXPIRE: %d", CA_EXPIRE)
        logger.debug("CA_BUFFER_TIME: %d", CA_BUFFER_TIME)
        logger.debug("domain: %s, ttl: %d", domain, ttl)

        pki_url = "%s/v1/%s/issue/%s" % (
            self.vault_addr,
            self.vault_pki,
            container.pki_role,
        )
        payload = dict(
            common_name=domain,
            ttl=str(ttl),
        )

        if other_names:
            other_names = ",".join(list(set(other_names) - {domain}))
            payload["alt_names"] = other_names

        logger.debug(str(pki_url))
        logger.debug(str(payload))

        logger.debug("requesting..")
        result = requests.post(
            pki_url,
            json=payload,
            headers={"X-Vault-Token": vault_token, "Content-Type": "application/json"},
        ).json()
        logger.debug("responded.")

        if "errors" in result:
            raise ValueError("\n".join(result.get("errors")))

        crt_file = cert_file(cert_name)
        key_file = cert_file(cert_name, ext="key")

        logger.debug(crt_file)
        logger.debug(key_file)

        with open(crt_file, "w") as f:
            f.write(result.get("data").get("certificate"))
        with open(key_file, "w") as f:
            f.write(result.get("data").get("private_key"))
        os.chmod(key_file, 0o600)

        return os.path.isfile(key_file)
