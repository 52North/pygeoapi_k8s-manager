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
# Substantial parts of this file are based on pygeoapi-kubernetes-papermill
# (https://github.com/eoxhub-workspaces/pygeoapi-kubernetes-papermill).
# pygeoapi-kubernetes-papermill is copyrighted by EOX IT Services GmbH
# (https://eox.at) and published under the MIT license.
# =================================================================
import datetime
import logging
import os
import re
from http import HTTPStatus
from typing import TypedDict

from kubernetes.client import (
    CoreV1Api,
    V1JobStatus,
    V1Pod,
)
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


def parse_annotation_key(key: str) -> str | None:
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


def job_status_from_k8s(status: V1JobStatus) -> JobStatus:
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


class JobDict(TypedDict, total=False):
    identifier: str
    message: str
    parameters: dict
    process_id: str
    status: str
    created: str | None
    started: str | None
    updated: str | None
    finished: str | None


def hide_secret_values(dictionary: dict[str, str]) -> dict[str, str]:
    def transform_value(key, value):
        return "*" if any(trigger in key.lower() for trigger in ["secret", "key", "password", "token"]) else value

    return {key: transform_value(key, value) for key, value in dictionary.items()}


def now_str() -> str:
    return datetime.datetime.now(datetime.UTC).strftime(DATETIME_FORMAT)


class ProcessorClientError(ProcessorExecuteError):
    http_status_code = HTTPStatus.BAD_REQUEST


def _value_matches_schema_type(value, schema_type: str) -> bool:
    # bool is a subclass of int, so check it before integer/number
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    # unknown/undeclared type -> do not enforce
    return True


def validate_process_inputs(
    data: dict | None,
    declared_inputs: dict,
    skip_keys: frozenset[str] = frozenset(),
) -> None:
    """
    Validate execution inputs against the process input declarations.

    For every declared input (except those in `skip_keys`):
    - if it is required (`minOccurs` >= 1, default 1) it MUST be present in `data`;
    - if present, its value MUST match the declared `schema.type`; for `maxOccurs` > 1
      a list whose items each match the type is accepted.

    Undeclared keys in `data` are allowed (the GenericImageProcessor forwards arbitrary
    inputs to the job container).
    Raises `ProcessorClientError` on the first violation.
    """
    data = data or {}
    for name, declaration in declared_inputs.items():
        if name in skip_keys:
            continue
        if name not in data:
            if declaration.get("minOccurs", 1) >= 1:
                raise ProcessorClientError(user_msg=f"Missing required input: '{name}'")
            continue
        schema_type = declaration.get("schema", {}).get("type")
        if schema_type is None:
            continue
        value = data[name]
        if declaration.get("maxOccurs", 1) != 1 and isinstance(value, list) and schema_type != "array":
            items = value
        else:
            items = [value]
        for item in items:
            if not _value_matches_schema_type(item, schema_type):
                raise ProcessorClientError(
                    user_msg=(f"Invalid type for input '{name}': expected '{schema_type}', got '{type(item).__name__}'")
                )


def get_logs_for_pod(
    pod: V1Pod,
    k8s_core_api: CoreV1Api | None = None,
) -> str:
    if k8s_core_api is None:
        k8s_core_api = CoreV1Api()
    received_logs_from_at_least_one_container = False
    logs = f"Logs of pod '{pod.metadata.name}'"
    if pod.spec.init_containers:
        for init_container in pod.spec.init_containers:
            container_log = k8s_core_api.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                container=init_container.name,
            )
            logs += f"\nInit Container '{init_container.name}'\n{container_log}"
            if container_log is not None:
                received_logs_from_at_least_one_container = True
    for container in pod.spec.containers:
        container_log = k8s_core_api.read_namespaced_pod_log(
            name=pod.metadata.name,
            namespace=pod.metadata.namespace,
            container=container.name,
        )
        logs += f"\nContainer '{container.name}'\n{container_log}"
        if container_log is not None:
            received_logs_from_at_least_one_container = True
    return logs if received_logs_from_at_least_one_container else None
