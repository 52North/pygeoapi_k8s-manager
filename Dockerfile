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

WORKDIR /k8s-manager

COPY requirements-docker.txt .
RUN python3 -m pip install -r requirements-docker.txt

COPY . .
RUN python3 -m pip install . \
 && rm -rv /k8s-manager

WORKDIR /pygeoapi

ARG GIT_COMMIT=commit-undefined
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

ARG BUILD_DATE=build-date-undefined
LABEL org.opencontainers.image.created="${BUILD_DATE}"

COPY pygeoapi-config.yaml local.config.yml

# Add build info to deployed version available via pygeoapi-context-path/static/info.txt
ARG INFO_FILE=pygeoapi/static/info.txt
ARG GIT_BRANCH=branch-undefined
ARG GIT_TAG=tag-undefined
RUN touch "${INFO_FILE}" \
 && echo "BUILD INFO" > "$INFO_FILE" \
 && echo "timestamp: $BUILD_DATE" >> "$INFO_FILE" \
 && echo "git hash: $GIT_COMMIT" >> "$INFO_FILE" \
 && echo "git branch: $GIT_BRANCH" >> "$INFO_FILE" \
 && echo "git tag: $GIT_TAG" >> "$INFO_FILE" \
 && echo "pygeoapi: $(pygeoapi --version)" >> "$INFO_FILE" \
 && cat ${INFO_FILE}

RUN sed -i '/{{ version }}/a \
 \(<a title="info" id="showInfo" href="{{ config["server"]["url"] }}/static/info.txt">info</a>\)\
 <script>\
 document.getElementById("showInfo").addEventListener("click", function(event) {\
   event.preventDefault();\
   fetch("{{ config["server"]["url"] }}/static/info.txt")\
     .then(response => response.text())\
     .then(data => {\
       alert(data);\
     })\
     .catch(error => {\
       alert("Error loading the file: " + error);\
     });\
 });\
 </script>' /pygeoapi/pygeoapi/templates/_base.html
