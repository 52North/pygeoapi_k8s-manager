FROM geopython/pygeoapi:0.19.0

ENV VERSION=0.1

LABEL maintainer="Jürrens, Eike Hinderk <e.h.juerrens@52north.org>" \
      org.opencontainers.image.authors="Jürrens, Eike Hinderk <e.h.juerrens@52north.org>" \
      org.opencontainers.image.url="https://github.com/52North/pygeoapi-k8s-manager.git" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.vendor="52°North GmbH" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.ref.name="52north/pygeoapi-k8s-manager" \
      org.opencontainers.image.title="52°North pygeoapi k8s-manager" \
      org.opencontainers.image.description="Extends pygeoapi by a manager for kubernetes jobs and a process to execute any container image on a cluster"

#
# Fight OS CVEs
#
RUN apt-get update \
&& apt-get upgrade -y \
&& apt-get dist-upgrade -y \
&& apt-get clean \
&& apt autoremove -y  \
&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY . .
RUN python3 -m pip install .

ARG GIT_COMMIT
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

ARG BUILD_DATE
LABEL org.opencontainers.image.created="${BUILD_DATE}"

COPY pygeoapi-config.yaml local.config.yml
