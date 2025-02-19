import datetime
import json
import logging
import re
from typing import Optional, TypedDict

from pygeoapi.util import (
    JobStatus
)

from pygeoapi.process.manager.base import (
    DATETIME_FORMAT
)

from kubernetes import (
    client as k8s_client
)


LOGGER = logging.getLogger(__name__)


def current_namespace():
    # getting the current namespace like this is documented, so it should be fine:
    # https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/
    # FIXME: works only for in-cluster set-up, hence some error handling might be useful
    return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

_ANNOTATIONS_PREFIX = "pygeoapi.io/"

def parse_annotation_key(key: str) -> Optional[str]:
    matched = re.match(f"^{_ANNOTATIONS_PREFIX}(.+)", key)
    return matched.group(1) if matched else None


def format_annotation_key(key: str) -> str:
    return f"{_ANNOTATIONS_PREFIX}{key}"

_JOB_NAME_PREFIX = "pygeoapi-job-"

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
        "status": str,
        "message": str,
        "job_start_datetime": Optional[str],
        "job_end_datetime": Optional[str],
    },
    total=False,
)


def hide_secret_values(dictionary: dict[str, str]) -> dict[str, str]:
    def transform_value(key, value):
        return (
            "*"
            if any(trigger in key.lower() for trigger in ["secret", "key", "password"])
            else value
        )

    return {key: transform_value(key, value) for key, value in dictionary.items()}


def now_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(DATETIME_FORMAT)
