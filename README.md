# openresty

nginx with lua script hooks.

This image builds upon previous nginx reverse proxy images. This one uses a container's environment variables to serve it at the requested FQDN while also generating a TLS certificate from a hashicorp `vault` (provided that AppRole, PKI role, and policy exist).

Internally, this container runs three components, managed by `supervisord`, and started in a particular order by the startup script `start.sh`.

First is the [openresty](https://openresty.org/en/) fork of nginx. If you've used nginx previously, it'll feel the same, but with Lua hooks (see `./example/`).

Second is a docker event watcher (`gen_watch.py`). It watches for changes in container states (starting and stopping) and acting upon them. When well-configured, the running containers may regenerate an nginx configuration file and SIGHUP the nginx. As needed, a TLS certificate will be generated for the requested domain through the configured hashicorp `vault` (which can be done several ways).

The last piece to this proxy is a listener on port `44380` (`gen_listener.py: 443 + 80`). With it, one can trigger the regeneration of a certificate using an AppRole secret-id and something to identify the container with (domain, name, image, etc). Use this to rotate certificates without stopping the service.

This container may choose to have no vault privilege; When using vault AppRoles, it only needs to know which vault to talk to and he rest is handed down by the running containers or through its listener endpoint. When safe to do so, issuing a `VAULT_TOKEN` to the proxy can be a time-saver.

## Configuring the proxy

See `docker-compose.yml` as an example. The nginx volumes are optional, but borrowing the docker.sock is necessary to catch events. The only ENV var needed is `VAULT_ADDR`.

## Configuring containers

To have a container served under it's desired name, some ENV vars are needed (some may alternatively be image labels). `SERVICE_FQDN` or `VIRTUAL_HOST` should supply a FQDN to serve as. There are some alternative methods for making an FQDN, but just use one of those and forget I said that. Dive into `confgen/__init__.py` for that and a few other options for additional SANs and a few other features.

`TODO: doc image & container label options`

`TODO: doc custom conf inclusions via conf/$FQDN/*.conf`

In line with vault's documented flow, the container is expected to have an AppRole role-id baked in, and expected here as `PKI_ROLE_ID`. This could also be given at run-time if the PKI setup is done in a playbook at the same time as launch, for example. No biggie. The vault approle to authenticate against is assumed to be the service's FQDN (ie, `/v1/approle/issue/foo.bar.com`) or the override value `PKI_ROLE`.

When launched, the ops-code should supply a `PKI_SECRET_ID` for that role to the launched container. That secret-id will be burned after use (or be dead on arrival). Restarting a container will not help if a certificate could not be generated. Should the proxy container restart, volumed certificates will remain in play, so containers should come back up; but should the volume not exist, they'll need updates or a relaunch.

```
# PKI example
# PKI_ROLE_ID could be given or baked into the image
# PKI_ROLE is assumed to be $VIRTUAL_HOST unless given

docker run -d \
  --name pypicloud \
  -e VIRTUAL_HOST=pypi.bibby.local \
  -e PKI_SECRET=${VAULT_APPROLE_SECRET?"Getting the secret is your responsibility"} \
  bibby/pypicloud
```

If you already have a cert, or you're cool with a wildcard cert, *and one exists* in the cert volume, you can specify the cert to use, circumventing the vault interaction.

```
# just use wildcard.crt
# ordinarily would have sought pypi.bibby.local.crt

docker run -d \
  --name pypicloud \
  -e VIRTUAL_HOST=pypi.bibby.local \
  -e CERT_NAME=wildcard.crt \
  bibby/pypicloud
```


As a certificate ages, it may be replaced without cycling the proxy container or target container through the listener endpoint: `http://{proxy}:44380/cert` .

The expected payload is POST/PUT json containing a `secret_id` and one of `[domain, virtual_host, container_name, image, cert_name]` to identify the target container with.

```
$ http PUT localhost:44380/cert container_name=hello secret_id=$SECRET_ID
{
    "regen": true,
    "updated": "hello.mydomain.com"
}
```

When successful, the new cert & key should exist and the nginx process SIGHUP'd again to put them into service.

Certificates are issued with a lifespan of six months `TODO: make configurable`. The longer the lifespan, the longer the window is to potentially request issuance of a certificate that would exceed the lifespan of the issuing CA, which will not work. Therefore, if the expiration time of your signing CA is known, it would be beneficial to inform this container so that it issue a cert successfully.

```
CA_EXPIRE = {timestamp, ie, 1644682156}  # expiration of the CA
CA_BUFFER_TIME = {seconds, Default = 3600 * 3 (3 hours)} # grace period

# default behavior is to issue certs with a expiration of six months OR
# up to 3 hours before the CA expires, to avoid issues
# around pushing too close that boundary
```

### One Container, Multiple domains / ports / certs

If you find yourself with a container that needs to serve off multiple ports, and you want all the free SSL proxying goodness, it's now possible; but with a few caveats.

To configure a second (or further up to 6) domain, include environment variables prefixed with an ordinal and it will loop around to treat each domain as a separate entity. For example, this three-domain container:

```
test_service:
  container_name: test_service
  image: testing/hello-http
  environment:
    SERVICE_FQDN: hello.mydomain.com
    SECOND_SERVICE_FQDN: hello-alt.mydomain.com
    SECOND_VIRTUAL_PORT: 2222
    THIRD_SERVICE_FQDN: hello-alt2.mydomain.com
    THIRD_CERT_NAME: hello.mydomain.com.crt
    THIRD_VIRTUAL_PORT: 3333
    ...
```

Here, `SECOND_`, `THIRD_`, etc are used as a replacement environment for a duplicate container-consideration during nginx conf generation.

Things to be aware of:

- `VIRTUAL_PORT` is assumed to be the *first* one exposed. Specify the target port as required.

- `SERVICE_FQDN / VIRTUAL_HOST` *ought* to be different than the main. With this proxy, containers with the same FQDN are entered into a round-robin load-balancing block for a singular service, which may not be what you want. Using a subdomain off-the-main or entirely unique domain name for the alternate port is recommended.

- `CERT_NAME` may be used to share one certificate among the several exposures, so long as it supports all of the names given as FQDNs. **You can skip the whole cert generation process** by dropping a pre-generated certificate into the cert volume (for instance, a wildcard cert), and include it by name as needed.

- Ordinals are parsed in succession to reduce overhead. So if a `THIRD_` is configured, but a `SECOND_` is not present *or is not valid*, then the `THIRD_` will not be considered.

`TODO: doc KNOWN_ROOTS as pertains to SNI domains ; https://service/ `


# Logs

Two logging vars:

```
# (debug|info|warn|error)
LOG_LEVEL: info          # log level of the confgen/listener
OPENRESTY_LOG_LEVEL: warn # log level of the nginx proxy error log
```

# VTS

[VirtualHost Traffic Status (VTS)](https://nginx-extras.getpagespeed.com/modules/vts/) is a extension module for nginx that reports traffic status. This module is installed, and can be controlled with ENV vars on the proxy. When enabled, statistics are visible at `https://{SOME_FQDN}/_status` .

```
VTS_ENABLED=1      # (0|1; Default=1, VTS enabled at VTS_PATH)
VTS_PATH="_status" # The path to see VTS (on every domain)
VTS_USER_AGENT=0   # More stats for user agents
VTS_URIS=0         # More stats for URIs (big perf hit!)
VTS_RESET_DB=0     # VTS data is persistent; enabling
                   # this will reset the DB once at startup
```

# Graylog

External log aggregators can be nice. Graylog is one that comes pre-configured (but disabled
by default) as an example. See `service_log.tpl` for enabling a log service, and `log_fmts.tpl`
for service-specific log formats.

```
GRAYLOG_ENABLED=0    # (0|1; Default=0) Send logs to Graylog
GRAYLOG_DOMAIN=''    # Domain of your Graylog server
GRAYLOG_PORT_ACCESS  # (Default = 12401) Access log receiver port
GRAYLOG_PORT_ERROR   # (Default = 12402) Error log receiver port
```

To include your own logger, look for the variables above in:
- Dockerfile
- confen/templates/conf.tpl
- ./nginx.conf (find `log_format graylog2_json`)


### glhf
