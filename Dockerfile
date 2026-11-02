ARG BASE_IMAGE=python:3.12-slim-trixie@sha256:6b25cbe6577518889d553cdd5a5da97d259348d8f6e45b527dd731caaba27a07
ARG DOCKER_CLI_IMAGE=docker:29.9.2-cli@sha256:5e6baf67325a79f64ed3bed6863954d5e05d0f3d4e57cbdb14809346814bbfdb
ARG COMPOSE_BUILD_IMAGE=golang:1.26.10-bookworm@sha256:632dff7351799a5a9954a48dc06670ade72ee44e8c351cdc0e5a57af2fea21af
FROM ${DOCKER_CLI_IMAGE} AS docker_cli
FROM ${COMPOSE_BUILD_IMAGE} AS compose_security
WORKDIR /src
ADD --checksum=sha256:2293b570f258dfc6e38e0bfdd3fa0e710324a7cf0449994304b524af8fb4f06c https://codeload.github.com/docker/compose/tar.gz/6cbc19a3fd59e305fb814dca4d854a4fb67d2941 /compose-source.tar.gz
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN tar -xzf /compose-source.tar.gz --strip-components=1 -C /src \
    && go mod edit -require=golang.org/x/net@v0.62.0 \
    && go build -mod=mod -trimpath -ldflags '-w -X github.com/docker/compose/v5/internal.Version=v5.6.1-mcj.2' -o /out/docker-compose ./cmd \
    && go list -mod=mod -deps ./cmd > /out/docker-compose-packages.txt \
    && go list -mod=mod -m all > /out/docker-compose-modules.txt \
    && mkdir -p /out/docker-compose-licenses \
    && find /go/pkg/mod -type f \( -iname 'license*' -o -iname 'copying*' -o -iname 'notice*' -o -iname 'copyright*' \) -exec cp --parents '{}' /out/docker-compose-licenses/ \;
FROM ${BASE_IMAGE}
ARG APP_VERSION=1.0.0
ARG BUILD_REVISION=unknown
ARG BUILD_CREATED=unknown
LABEL org.opencontainers.image.title="MCJ Manager" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.authors="Roman Glos" \
      org.opencontainers.image.description="Minecraft Java server management for UGREEN NAS. Independent project." \
      org.opencontainers.image.source="https://github.com/Railsimulatornet/UGREEN-NAS-Minecraft-Java-Manager" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /opt/mcj
COPY requirements.txt /opt/mcj/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check --upgrade pip==26.2.0 \
    && pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && pip check \
    && pip uninstall --yes pip \
    && python -c "import shutil,sysconfig; shutil.rmtree(sysconfig.get_path('stdlib')+'/ensurepip')" \
    && useradd --no-create-home --uid 1009 --gid 10 --shell /usr/sbin/nologin mcj
COPY --chown=0:10 mcj /opt/mcj/mcj
COPY --chown=0:10 start-game.sh /opt/mcj/start-game.sh
COPY --chown=0:10 tools /opt/mcj/tools
COPY --chown=0:10 deploy /opt/mcj/deploy
COPY --chown=0:10 artifacts /opt/mcj/artifacts
COPY --chown=0:10 compose.yaml .dockerignore Dockerfile NOTICE.txt LICENSE /opt/mcj/
COPY --chown=0:10 licenses /opt/mcj/licenses
COPY --from=docker_cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=compose_security /out/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=compose_security /src/LICENSE /opt/mcj/licenses/docker-compose-LICENSE
COPY --from=compose_security /out/docker-compose-packages.txt /opt/mcj/licenses/docker-compose-packages.txt
COPY --from=compose_security /out/docker-compose-modules.txt /opt/mcj/licenses/docker-compose-modules.txt
COPY --from=compose_security /out/docker-compose-licenses /opt/mcj/licenses/docker-compose-dependencies
RUN chmod -R a+rX /opt/mcj
USER 1009:10
RUN python -c "import mcj, mcj.web; from mcj.application_update import template; assert 'application-update' in template()"
RUN docker compose version
CMD ["uvicorn","mcj.entry:app","--host","0.0.0.0","--port","8090","--no-access-log","--no-proxy-headers"]
