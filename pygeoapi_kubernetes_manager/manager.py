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
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import (
    Any,
    Optional,
    cast,
)

from kubernetes import (
    client as k8s_client,
)
from kubernetes import (
    config as k8s_config,
)
from pygeoapi.process.base import (
    BaseProcessor,
    JobNotFoundError,
    JobResultNotFoundError,
    ProcessorExecuteError,
)
from pygeoapi.process.manager.base import (
    BaseManager,
    RequestedResponse,
    Subscriber,
)
from pygeoapi.util import (
    DATETIME_FORMAT,
    JobStatus,
)

from .finalizer import KubernetesFinalizerController
from .util import (
    JobDict,
    current_namespace,
    format_annotation_key,
    format_job_name,
    format_log_finalizer,
    hide_secret_values,
    is_k8s_job_name,
    job_status_from_k8s,
    now_str,
    parse_annotation_key,
)

LOGGER = logging.getLogger(__name__)

K8S_ANNOTATION_KEY_JOB_START = "started"
K8S_ANNOTATION_KEY_JOB_END = "finished"
K8S_ANNOTATION_KEY_JOB_UPDATED = "updated"


class KubernetesProcessor(BaseProcessor):
    @dataclass()
    class JobPodSpec:
        pod_spec: k8s_client.V1PodSpec
        extra_annotations: dict[str, str]

    def __init__(self, processor_def, process_metadata):
        super().__init__(processor_def, process_metadata)
        self.mimetype = processor_def["mimetype"] if "mimetype" in processor_def else "application/json"
        self.tolerations: list = processor_def["tolerations"] if "tolerations" in processor_def else None
        self.is_check_auth = processor_def["check_auth"] if "check_auth" in processor_def else None

    def _add_tolerations(self, job_spec: JobPodSpec):
        if self.tolerations:
            tolerations: list[k8s_client.V1Toleration] = [
                k8s_client.V1Toleration(**toleration) for toleration in self.tolerations
            ]
            job_spec.pod_spec.tolerations = tolerations
        return job_spec

    def check_auth(self) -> bool:
        """
        Returns True, if auth "token" should be verified.

        Can be configured in the processor_def via key "check_auth" or by overriding this function.
        """
        return self.is_check_auth if self.is_check_auth is not None else True

    def create_job_pod_spec(
        self,
        data: dict,
        job_name: str,
    ) -> JobPodSpec:
        """
        Returns a definition of a job as well as result handling.
        Currently the only supported way for handling result is for the processor
        to provide a fixed link where the results will be available (the job itself
        has to ensure that the resulting data ends up at the link)
        """
        raise NotImplementedError()

    def execute(self):
        raise NotImplementedError("Kubernetes Processes can't be executed directly, use KubernetesManager")


class KubernetesManager(BaseManager):
    """
    Implements pygeoapi.process.manager.base.BaseManager and uses
    the kubernetes API server as processing backend.
    """

    def __init__(self, manager_def: dict) -> None:
        super().__init__(manager_def)
        #
        # base config
        #
        self.is_async = True
        self.supports_subscribing = False
        #
        # k8s configuration
        # 0. check for test call
        # 1. try ~/.kube/config
        # 2. try service account
        # TODO: maybe switch order to try service account first
        #
        if manager_def.get("mode") == "test":
            self.namespace = "test"
        else:
            try:
                k8s_config.load_kube_config()
            except Exception as e:
                LOGGER.error(e)
                # load_kube_config might throw anything
                k8s_config.load_incluster_config()

            self.namespace = current_namespace()
            self.batch_v1 = k8s_client.BatchV1Api()
            self.core_api = k8s_client.CoreV1Api()
        # set logging for dependencies
        if manager_def.get("logging"):
            for lib, level in manager_def.get("logging").items():
                LOGGER.debug(f"Set log level '{level}' for library '{lib}'")
                logging.getLogger(lib).setLevel(getattr(logging, level.upper(), logging.WARNING))
        #
        # start finalizer controller
        if manager_def.get("finalizer_controller"):
            self.finalizer_controller = KubernetesFinalizerController(
                os.path.join(
                    tempfile.gettempdir(),
                    "pygeoapi-k8s-job-manager-one-finalizer-thread",
                ),
                self.namespace,
            )
            self.finalizer_controller.start_watching()
        else:
            self.finalizer_controller = None

    def add_job(self, job_metadata):
        # For k8s, add_job is implied by executing the job
        return

    def update_job(self, processid, job_id, update_dict):
        # we could update the metadata by changing the job annotations
        raise NotImplementedError("Currently there's no use case for updating k8s jobs")

    def get_jobs(self, status=None, limit=None, offset=None):
        """
        Get process jobs, optionally filtered by status

        :param status: job status (accepted, running, successful,
                       failed, results) (default is all)
        :param limit: number of jobs to return
        :param offset: pagination offset

        :returns: dict of list of jobs (identifier, status, process identifier)
                  and numberMatched
        """

        # NOTE: pagination should be pushed to the kubernetes api,
        #       but it doesn't support regex matching on the job name
        #       https://kubernetes.io/docs/concepts/overview/working-with-objects/field-selectors/#supported-operators
        #
        # get all jobs matching name requirement and sort by start time
        #
        k8s_jobs = sorted(
            (
                k8s_job
                for k8s_job in k8s_client.BatchV1Api()
                .list_namespaced_job(
                    namespace=self.namespace,
                )
                .items
                if is_k8s_job_name(k8s_job.metadata.name)
            ),
            key=get_start_time_from_job,
            reverse=True,
        )

        number_matched = len(k8s_jobs)
        LOGGER.debug(
            f"Received {number_matched} jobs from cluster. Applying limit '{limit}' and offset '{offset}', if given."
        )

        # NOTE: need to paginate before expensive single job serialization
        if offset:
            k8s_jobs = k8s_jobs[offset:]

        if limit:
            k8s_jobs = k8s_jobs[:limit]

        return {
            "jobs": [job_from_k8s(k8s_job, job_message(self.namespace, k8s_job)) for k8s_job in k8s_jobs],
            "numberMatched": number_matched,
        }

    def get_job(self, job_id) -> Optional[JobDict]:
        """
        Returns the actual output from a completed process

        :param job_id: job identifier

        :returns: `dict`  # `pygeoapi.process.manager.Job`
        """

        try:
            k8s_job: k8s_client.V1Job = self.batch_v1.read_namespaced_job(
                name=format_job_name(job_id=job_id),
                namespace=self.namespace,
            )
            return job_from_k8s(k8s_job, job_message(self.namespace, k8s_job))
        except k8s_client.rest.ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                raise JobNotFoundError(f"Job with id '{job_id}' not found.") from e
            else:
                raise

    def get_job_result(self, job_id) -> tuple[Optional[Any], Optional[str]]:
        """
        Returns the actual output from a completed process

        :param job_id: job identifier

        :returns: `tuple` of mimetype and raw output

        :raises: JobResultNotFoundError if job is not successful
        """
        job = self.get_job(job_id=job_id)

        if job is None:
            # should not happen and be handled already in self.get_job()
            raise JobNotFoundError(f"No job with id '{job_id}' found!")
        elif (JobStatus[job["status"]]) != JobStatus.successful:
            raise JobResultNotFoundError(
                f"No results for job '{job_id}' with state '{JobStatus[job['status']].value}' found."
            )
        else:
            # ATM: get pod and pod logs and return them json encoded
            pod: k8s_client.V1Pod = pod_for_job_id(self.namespace, job["identifier"])
            if pod is None:
                msg = f"Pod not found for job '{job_id}'"
                LOGGER.error(msg)
                raise JobResultNotFoundError(f"Pod not found for job '{job_id}'")
            LOGGER.debug(f"metadata.name   : '{pod.metadata.name}'")
            LOGGER.debug(f"container name  : '{pod.spec.containers[0].name}")
            logs = k8s_client.CoreV1Api().read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                container=pod.spec.containers[0].name,
            )
            if logs is None:
                msg = f"Could not retrieve logs for job '{job_id}'"
                LOGGER.error(msg)
                raise JobResultNotFoundError(msg)
            LOGGER.debug(f"logs            : '{logs}'")
            return (None, logs)

    def _execute_handler_sync(
        self,
        p: BaseProcessor,  # EHJ: why BaseProcessor here, if it is passed directly into a
        # another function that supports/expects k8s Processors only!
        job_id,
        data_dict: dict,
        requested_outputs: Optional[dict] = None,
        subscriber: Optional[Subscriber] = None,
        requested_response: Optional[RequestedResponse] = RequestedResponse.raw.value,  # noqa
    ) -> tuple[Optional[str], Optional[Any], JobStatus]:
        """
        Synchronous execution handler

        Executes job asynchronously, and checks every two seconds
        the job status until the job is finished, vanished, or failed.
        Vanish is a job, if deleted from k8s without interaction of
        this manager.

        :param p: `pygeoapi.t` object
        :param job_id: job identifier
        :param data_dict: `dict` of data parameters

        :returns: tuple of MIME type, response payload and status
        """
        self._execute_handler_async(p=p, job_id=job_id, data_dict=data_dict, subscriber=subscriber)

        while True:
            time.sleep(2)
            job = self.get_job(job_id=job_id)
            if not job:
                LOGGER.warning(f"Job {job_id} has vanished")
                status = JobStatus.failed
                break

            status = JobStatus[job["status"]]
            if status not in (JobStatus.running, JobStatus.accepted):
                # return to caller if job is failed or successful
                break

        mimetype, result = self.get_job_result(job_id=job_id)

        return (mimetype, result, status)

    def _execute_handler_async(
        self,
        p: KubernetesProcessor,
        job_id,
        data_dict,
        requested_outputs: Optional[dict] = None,
        subscriber: Optional[Subscriber] = None,
        requested_response: Optional[RequestedResponse] = RequestedResponse.raw.value,  # noqa
    ) -> tuple[str, dict, JobStatus]:
        """
        In practice k8s jobs are always async.

        :param p: `pygeoapi.process` object
        :param job_id: job identifier
        :param data_dict: `dict` of data parameters

        :returns: tuple of None (i.e. initial response payload)
                  and JobStatus.accepted (i.e. initial job status)
        """
        if not isinstance(p, KubernetesProcessor):
            raise NotImplementedError(
                f"'{type(p).__name__}' is not a KubernetesProcessor as required by KubernetesManager."
            )

        if p.check_auth():
            self._check_auth_token(data_dict)

        add_finalizer = self.finalizer_controller is not None
        job = create_job_body(p, job_id, data_dict, add_finalizer)

        LOGGER.debug(f"Trying to create job in namespace '{self.namespace}': '{job}")
        self.batch_v1.create_namespaced_job(body=job, namespace=self.namespace)
        LOGGER.info("Add job %s in ns %s", job.metadata.name, self.namespace)
        return ("application/json", {}, JobStatus.accepted)

    def _check_auth_token(self, data_dict: dict):
        key = "PYGEOAPI_K8S_MANAGER_API_TOKEN"
        token = data_dict["token"]
        if token is None:
            raise ProcessorExecuteError("Identify yourself with valid token!")

        if token != os.getenv(key):
            msg = "ACCESS DENIED: wrong token"
            LOGGER.error(msg)
            LOGGER.debug(
                f"WRONG INTERNAL API TOKEN '{token}' ('{type(token)}') != '{os.getenv(key)}' ('{type(os.getenv(key))}')"
            )
            raise ProcessorExecuteError(msg)


def create_job_body(
    p: KubernetesProcessor, job_id: str, data_dict: dict, add_finalizer: bool = False
) -> k8s_client.V1Job:
    job_name = format_job_name(job_id=job_id)
    job_pod_spec = p.create_job_pod_spec(
        data=data_dict,
        job_name=job_name,
    )

    if p.tolerations is not None and len(p.tolerations) > 0:
        job_pod_spec = p._add_tolerations(job_pod_spec)

    now = now_str()
    annotations = {
        "identifier": job_id,
        "process_id": p.metadata.get("id"),
        K8S_ANNOTATION_KEY_JOB_START: now,
        K8S_ANNOTATION_KEY_JOB_UPDATED: now,
        "mimetype": p.mimetype if p.mimetype else "application/json",
        **job_pod_spec.extra_annotations,
    }

    return k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            annotations={format_annotation_key(k): v for k, v in annotations.items()},
        ),
        spec=k8s_client.V1JobSpec(
            template=k8s_client.V1PodTemplateSpec(
                # metadata=k8s_client.V1ObjectMeta(labels=job_pod_spec.extra_labels),
                metadata=k8s_client.V1ObjectMeta(
                    finalizers=[format_log_finalizer()] if add_finalizer is not None else None
                ),
                spec=job_pod_spec.pod_spec,
            ),
            backoff_limit=0,
            # TODO Could configurable (by job, processor, or global)
            # Lifetime of the job, NOT pod!
            # about 3 months (100 days)
            ttl_seconds_after_finished=60 * 60 * 24 * 100,
        ),
    )


def job_message(namespace: str, job: k8s_client.V1Job) -> Optional[str]:
    if job_status_from_k8s(job.status) == JobStatus.accepted:
        # if a job is in state accepted, it means that it can run right now
        # and the events can show why that is
        events: k8s_client.V1EventList = k8s_client.CoreV1Api().list_namespaced_event(
            namespace=namespace,
            field_selector=(f"involvedObject.name={job.metadata.name},involvedObject.kind=Job"),
        )
        if items := events.items:
            return items[-1].message

    if pod := pod_for_job(namespace, job):
        # everything can be null in kubernetes, even empty lists
        if pod.status.container_statuses:
            # we check only the state of the first container, because
            # our job pods only have one container at the moment
            state: k8s_client.V1ContainerState = pod.status.container_statuses[0].state
            interesting_states = [s for s in (state.waiting, state.terminated) if s]
            if interesting_states:
                return ": ".join(
                    filter(
                        None,
                        (
                            interesting_states[0].reason,
                            interesting_states[0].message,
                        ),
                    )
                )
    return None


def pod_for_job_id(namespace: str, job_id: str) -> Optional[k8s_client.V1Pod]:
    label_selector = f"job-name={format_job_name(job_id)}"
    LOGGER.debug(f"label_selector: '{label_selector}'")
    pods: k8s_client.V1PodList = k8s_client.CoreV1Api().list_namespaced_pod(
        namespace=namespace, label_selector=label_selector
    )
    return next(iter(pods.items), None)


def pod_for_job(namespace: str, job: k8s_client.V1Job) -> Optional[k8s_client.V1Pod]:
    label_selector = ",".join(f"{key}={value}" for key, value in job.spec.selector.match_labels.items())
    pods: k8s_client.V1PodList = k8s_client.CoreV1Api().list_namespaced_pod(
        namespace=namespace, label_selector=label_selector
    )

    return next(iter(pods.items), None)


def job_from_k8s(job: k8s_client.V1Job, message: Optional[str]) -> JobDict:
    """
    Converts k8s::job to pygeoapi::job
    """
    # annotations is broken in the k8s library, it's None when it is empty
    LOGGER.debug("Converting k8s job to pygeoapi job")
    annotations = job.metadata.annotations or {}
    LOGGER.debug(f"k8s job annotations: '{annotations}'")
    metadata_from_annotation = {
        parsed_key: v for orig_key, v in annotations.items() if (parsed_key := parse_annotation_key(orig_key))
    }
    LOGGER.debug(f"extracted pygeoapi annotations: '{metadata_from_annotation}'")
    if "mimetype" not in metadata_from_annotation:
        metadata_from_annotation["mimetype"] = "application/json"

    try:
        metadata_from_annotation["parameters"] = json.dumps(
            hide_secret_values(
                json.loads(
                    metadata_from_annotation.get("parameters", "{}"),
                )
            )
        )
    except json.JSONDecodeError:
        LOGGER.info("can't obfuscate parameters, not valid json", exc_info=True)
        # TODO throw Error here?

    status = job_status_from_k8s(job.status)
    start_time = get_start_time_from_job(job)
    completion_time = get_completion_time(job)
    completion_time = completion_time.strftime(DATETIME_FORMAT) if completion_time else None
    updated_time = completion_time if completion_time else start_time
    # default values in case we don't get them from metadata
    default_progress = "100" if status == JobStatus.successful else "1"

    return cast(
        JobDict,
        {
            # need this key in order not to crash, overridden by metadata_from_annotation:
            "identifier": "",
            "process_id": "",
            "parameters": "",
            "created": start_time,
            K8S_ANNOTATION_KEY_JOB_START: start_time,
            K8S_ANNOTATION_KEY_JOB_UPDATED: updated_time,
            K8S_ANNOTATION_KEY_JOB_END: completion_time,
            # NOTE: this is passed as string as compatibility with base manager
            "status": status.value,
            "message": message if message else "",
            "progress": default_progress,
            **metadata_from_annotation,
        },
    )


def get_start_time_from_job(job: k8s_client.V1Job) -> str:
    key = format_annotation_key(K8S_ANNOTATION_KEY_JOB_START)
    # if not available via annotations, use k8s object creation time
    start_time = (
        job.metadata.annotations.get(key, "")
        if job.metadata.annotations and job.metadata.annotations.get(key)
        else job.metadata.creation_timestamp
    )
    LOGGER.debug(f"found start time: {start_time}")
    return start_time


def get_completion_time(job: k8s_client.V1Job) -> Optional[datetime]:
    if job_status_from_k8s(job.status) == JobStatus.failed:
        # failed jobs have special completion time field
        return max(
            (
                condition.last_transition_time
                for condition in job.status.conditions
                if condition.type == "Failed" and condition.status == "True"
            ),
            default=None,
        )

    return job.status.completion_time
