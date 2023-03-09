FROM ubuntu:18.04

ARG RESTY_VERSION="1.13.6.1"
ARG RESTY_LUAROCKS_VERSION="2.4.3"
ARG RESTY_OPENSSL_VERSION="1.0.2k"
ARG RESTY_PCRE_VERSION="8.41"
ARG RESTY_VTS_VERSION="0.1.18"
ARG RESTY_J="1"
ARG RESTY_CONFIG_OPTIONS="\
    --with-file-aio \
    --with-http_addition_module \
    --with-http_auth_request_module \
    --with-http_dav_module \
    --with-http_flv_module \
    --with-http_geoip_module=dynamic \
    --with-http_gunzip_module \
    --with-http_gzip_static_module \
    --with-http_image_filter_module=dynamic \
    --with-http_mp4_module \
    --with-http_random_index_module \
    --with-http_realip_module \
    --with-http_secure_link_module \
    --with-http_slice_module \
    --with-http_ssl_module \
    --with-http_stub_status_module \
    --with-http_sub_module \
    --with-http_v2_module \
    --with-http_xslt_module=dynamic \
    --with-ipv6 \
    --with-mail \
    --with-mail_ssl_module \
    --with-md5-asm \
    --with-pcre-jit \
    --with-sha1-asm \
    --with-stream \
    --with-stream_ssl_module \
    --with-threads \
    --add-module=/tmp/nginx-module-vts-${RESTY_VTS_VERSION} \
    "
ARG RESTY_CONFIG_OPTIONS_MORE=""
ARG _RESTY_CONFIG_DEPS="--with-openssl=/tmp/openssl-${RESTY_OPENSSL_VERSION} --with-pcre=/tmp/pcre-${RESTY_PCRE_VERSION}"

ENV VAULT_ADDR="" \
    VAULT_TOKEN="" \
    VAULT_PKI="pki" \
    CA_EXPIRE=1635082659 \
    OPENRESTY_LOG_LEVEL=warn \
    TPL_DIR=/usr/src/confgen/templates \
    MAX_UPLOAD_SIZE=0 \
    REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt" \
    NGINX_PROXY_IGNORE=1 \
    NGINX_OPTION_PREFIX='openresty' \
    PYTHONWARNINGS='ignore' \
    VTS_ENABLED=1 \
    VTS_DB_DIR=/etc/nginx/db \
    VTS_URIS=0 \
    VTS_USER_AGENT=0 \
    VTS_RESET_DB=0 \
    VTS_PATH="_status" \
    GRAYLOG_ENABLED=0 \
    GRAYLOG_DOMAIN='' \
    GRAYLOG_PORT_ACCESS=12401 \
    GRAYLOG_PORT_ERROR=12402

EXPOSE 80 443 44380
LABEL openresty.proxy=true

VOLUME /etc/nginx/certs
VOLUME /etc/nginx/conf.d
VOLUME /etc/nginx/db

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      gettext-base \
      libgd-dev \
      libgeoip-dev \
      libncurses5-dev \
      libperl-dev \
      libreadline-dev \
      libxslt1-dev \
      make \
      perl \
      unzip \
      zlib1g-dev \
      python-pip \
      libssl-dev \
      libldap2-dev \
      supervisor

COPY requirements.txt /tmp/requirements.txt
RUN pip install -U pip setuptools
RUN pip install -U docker
RUN pip install \
    -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

WORKDIR /tmp

RUN curl -fSL https://www.openssl.org/source/openssl-${RESTY_OPENSSL_VERSION}.tar.gz -o openssl-${RESTY_OPENSSL_VERSION}.tar.gz \
    && tar xzf openssl-${RESTY_OPENSSL_VERSION}.tar.gz

RUN curl -fSL https://github.com/vozlt/nginx-module-vts/archive/v${RESTY_VTS_VERSION}.tar.gz -o  nginx-module-vts-${RESTY_VTS_VERSION}.tar.gz \
    && tar xzf nginx-module-vts-${RESTY_VTS_VERSION}.tar.gz

RUN curl -fSL https://sourceforge.net/projects/pcre/files/pcre/${RESTY_PCRE_VERSION}/pcre-${RESTY_PCRE_VERSION}.tar.gz/download -o pcre-${RESTY_PCRE_VERSION}.tar.gz \
    && tar xzf pcre-${RESTY_PCRE_VERSION}.tar.gz

RUN curl -fSL https://openresty.org/download/openresty-${RESTY_VERSION}.tar.gz -o openresty-${RESTY_VERSION}.tar.gz \
    && tar xzf openresty-${RESTY_VERSION}.tar.gz

RUN curl -fSL https://github.com/luarocks/luarocks/archive/refs/tags/v${RESTY_LUAROCKS_VERSION}.tar.gz -o luarocks-${RESTY_LUAROCKS_VERSION}.tar.gz \
    && tar xzf luarocks-${RESTY_LUAROCKS_VERSION}.tar.gz

WORKDIR /tmp/openresty-${RESTY_VERSION}

RUN ./configure -j${RESTY_J} ${_RESTY_CONFIG_DEPS} ${RESTY_CONFIG_OPTIONS} ${RESTY_CONFIG_OPTIONS_MORE} \
    && make -j${RESTY_J} \
    && make -j${RESTY_J} install

WORKDIR /tmp

RUN rm -rf \
    openssl-${RESTY_OPENSSL_VERSION} \
    openssl-${RESTY_OPENSSL_VERSION}.tar.gz \
    openresty-${RESTY_VERSION}.tar.gz openresty-${RESTY_VERSION} \
    pcre-${RESTY_PCRE_VERSION}.tar.gz pcre-${RESTY_PCRE_VERSION}

WORKDIR /tmp/luarocks-${RESTY_LUAROCKS_VERSION}
RUN ./configure \
        --prefix=/usr/local/openresty/luajit \
        --with-lua=/usr/local/openresty/luajit \
        --lua-suffix=jit-2.1.0-beta3 \
        --with-lua-include=/usr/local/openresty/luajit/include/luajit-2.1 \
    && make build \
    && make install

WORKDIR /tmp
RUN rm -rf luarocks-${RESTY_LUAROCKS_VERSION} luarocks-${RESTY_LUAROCKS_VERSION}.tar.gz \
    && DEBIAN_FRONTEND=noninteractive apt-get autoremove -y \
    && ln -sf /dev/stdout /usr/local/openresty/nginx/logs/access.log \
    && ln -sf /dev/stderr /usr/local/openresty/nginx/logs/error.log

ENV PATH=$PATH:/usr/local/openresty/luajit/bin/:/usr/local/openresty/nginx/sbin/:/usr/local/openresty/bin/

RUN opm get tokers/lua-resty-requests
RUN mkdir -p /var/log/supervisor

RUN luarocks-5.1 install openssl && \
    luarocks-5.1 install LuaLDAP

WORKDIR /usr/src

COPY confgen confgen
COPY *.py ./
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY start.sh /start.sh
COPY example /etc/nginx/example

CMD ["/bin/bash", "/start.sh"]
