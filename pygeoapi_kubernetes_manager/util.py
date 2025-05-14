# =================================================================
#
# Authors: Eike Hinderk Jürrens <e.h.juerrens@52north.org>
#
# Copyright (c) 2025 52°North Spatial Information Research GmbH
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================
import datetime
import logging
import os
import re
from http import HTTPStatus
from typing import Optional, TypedDict

from kubernetes import client as k8s_client
from pygeoapi.process.base import ProcessorExecuteError
from pygeoapi.util import (
    DATETIME_FORMAT,
    JobStatus,
)

LOGGER = logging.getLogger(__name__)


def current_namespace():
    # getting the current namespace like this is documented, so it should be fine:
    # https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/
    try:
        return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()
    except FileNotFoundError as e:
        # if not in cluster, env should be set, so check this
        ns_env_key = "PYGEOAPI_K8S_MANAGER_NAMESPACE"
        if ns_env_key in os.environ:
            return os.getenv(ns_env_key)
        else:
            raise KeyError(f"Required environment variable '{ns_env_key}' is missing.") from e


_ANNOTATIONS_PREFIX = "pygeoapi.io/"


def format_log_finalizer() -> str:
    return f"{_ANNOTATIONS_PREFIX}finalizer-log-retrieval"


def parse_annotation_key(key: str) -> Optional[str]:
    matched = re.match(f"^{_ANNOTATIONS_PREFIX}(.+)", key)
    return matched.group(1) if matched else None


def format_annotation_key(key: str) -> str:
    """
    https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/#syntax-and-character-set

    prefix/key: value

    len(prefix) <= 253
    len(key) <= 63
    """
    if len(key) > 63:
        raise ValueError(f"Specified key '{key}' is longer than allowed API limit 63: '{len(key)}'")
    return f"{_ANNOTATIONS_PREFIX}{key}"


_JOB_NAME_PREFIX = os.getenv("PYGEOAPI_K8S_MANAGER_JOB_NAME_PREFIX", "pygeoapi-job-")


def format_job_name(job_id: str) -> str:
    return f"{_JOB_NAME_PREFIX}{job_id}"


def is_k8s_job_name(job_name: str) -> bool:
    return job_name.startswith(_JOB_NAME_PREFIX)


def job_id_from_job_name(job_name: str) -> str:
    return job_name.replace(_JOB_NAME_PREFIX, "")


def job_status_from_k8s(status: k8s_client.V1JobStatus) -> JobStatus:
    # we assume only 1 run without retries
    # these "integers" are None if they are 0, lol
    if status.succeeded is not None and status.succeeded > 0:
        return JobStatus.successful
    elif status.failed is not None and status.failed > 0:
        return JobStatus.failed
    elif status.active is not None and status.active > 0:
        return JobStatus.running
    else:
        return JobStatus.accepted


JobDict = TypedDict(
    "JobDict",
    {
        "identifier": str,
        "message": str,
        "parameters": dict,
        "process_id": str,
        "status": str,
        "created": Optional[str],
        "started": Optional[str],
        "updated": Optional[str],
        "finished": Optional[str],
    },
    total=False,
)


def hide_secret_values(dictionary: dict[str, str]) -> dict[str, str]:
    def transform_value(key, value):
        return "*" if any(trigger in key.lower() for trigger in ["secret", "key", "password", "token"]) else value

    return {key: transform_value(key, value) for key, value in dictionary.items()}


def now_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(DATETIME_FORMAT)


class ProcessorClientError(ProcessorExecuteError):
    http_status_code = HTTPStatus.BAD_REQUEST
