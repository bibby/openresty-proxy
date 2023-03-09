import os
from flask import Flask, request, jsonify
from confgen.watcher import Watcher
from confgen.container import Container
from confgen.gen import CertGen
import logging

app = Flask(__name__)
logger = app.logger
watcher = Watcher()


@app.before_first_request
def setup_logging():
    log_level = logging.INFO
    user_log_level = os.environ.get('LOG_LEVEL', log_level)
    if not isinstance(user_log_level, int):
        level = getattr(logging, str(user_log_level).upper(), None)
        if isinstance(level, int):
            log_level = level
    app.logger.addHandler(logging.StreamHandler())
    app.logger.setLevel(log_level)


class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.route("/ping")
def hello():
    return "PONG!\n"


@app.route("/cert", methods=['POST', 'PUT'])
def cert_update():
    try:
        payload = request.json
        if not payload:
            raise ValueError("empty request or not json")

        validate_payload(payload)
        container = identify_container(payload)
        if not container:
            raise InvalidUsage("Container not found", status_code=404)

        CertGen.secret_updates[container.service_fqdn] = payload.get("secret_id")
        regen = watcher.generator.qualify_container(container, force_regen=True)
        watcher.generate_config(force=regen)

        return jsonify(regen=regen, updated=container.service_fqdn)
    except InvalidUsage:
        raise
    except Exception as e:
        raise InvalidUsage(str(e), status_code=400)


def validate_payload(payload):
    if not isinstance(payload, (dict,)):
        raise ValueError("Payload not the appropriate dict type. Is a: " + type(payload))
    if "secret_id" not in payload:
        raise ValueError("secret_id not found in payload. Won't be getting a new cert without one sadly.")

    optionals = ['domain', 'virtual_host', 'container_name', 'image', 'cert_name']
    has = []

    for opt in optionals:
        has.append(opt in payload)
    if not any(has):
        raise ValueError("Payload is missing something to identify the target. Need at least one of: " + str(optionals))


def identify_container(payload):
    def id_log(container_prop, payload_prop):
        logger.debug(
            " [%s] %s == %s : %s",
            payload_prop,
            container_prop,
            payload.get(payload_prop, ""),
            container_prop == payload.get(payload_prop, "")
        )

    for container in watcher.client.containers.list():
        container = Container(container)

        id_log(container.service_fqdn, "domain")
        if "domain" in payload and container.service_fqdn == payload["domain"]:
            return container

        id_log(container.service_fqdn, "cert_name")
        if "virtual_host" in payload and container.service_fqdn == payload["virtual_host"]:
            return container

        id_log(container.service_fqdn, "cert_name")
        if "cert_name" in payload and container.cert_name == payload["cert_name"]:
            return container

        id_log(container.name, "container_name")
        if "container_name" in payload and container.name == payload["container_name"]:
            return container

        id_log(container.image, "image")
        if "image" in payload and container.image == payload["image"]:
            return container


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=44380)
