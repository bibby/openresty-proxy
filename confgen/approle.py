import json
import logging
import os

import hvac
import requests

logger = logging.getLogger(__name__)
env = os.environ.get


def bail(msg):
    logger.error(msg)
    return None


def unwrap_file(secret_file):
    if not os.path.isfile(secret_file):
        return bail("secret file not found: " + str(secret_file))

    with open(secret_file, "r") as secret_handle:
        try:
            payload = json.loads(secret_handle.read())
        except json.JSONDecodeError:
            return bail("secret wasn't json or wasn't readable: " + str(secret_file))

    if "secret_id" not in payload:
        return bail("parsed secret contained no secret_id")

    return payload["secret_id"]


def unwrap_token(token):
    unwrap_client = hvac.Client(
        url=env("VAULT_ADDR"), verify=env("REQUESTS_CA_BUNDLE"), token=token
    )

    facts = unwrap_client.sys.unwrap()
    if facts:
        return facts.get("data").get("secret_id")


def login(role_id, secret_id):
    token = env("VAULT_TOKEN", None)
    if token:
        return token

    for prop in ["VAULT_ADDR"]:
        if not env(prop, None):
            return bail(
                prop + " is not set. No appRole exchange can happen without it."
            )

    if os.path.isfile(secret_id):
        secret_id = unwrap_file(secret_id)
    elif len(secret_id) == 26:
        try:
            logger.debug("unwrapping: " + secret_id)
            unwrapped = unwrap_token(secret_id)
            logger.debug("unwrapped: " + str(unwrapped))
            secret_id = unwrapped
        except Exception as e:
            logger.exception(e)
            pass

    login_url = "{vault_addr}/v1/auth/approle/login".format(
        vault_addr=env("VAULT_ADDR")
    )
    logger.debug(login_url)

    payload = dict(
        secret_id=secret_id,
        role_id=role_id,
    )
    logger.debug(str(payload))

    try:
        response = requests.post(login_url, json=payload).json()
    except Exception as e:
        logger.exception(e)
        return bail("Failed requesting a vault auth login. (Secret-Id expired?)")

    if "errors" in response:
        return bail("\n".join(response["errors"]))

    if "auth" not in response:
        return bail("Response contains no auth object")

    return response["auth"]["client_token"]
