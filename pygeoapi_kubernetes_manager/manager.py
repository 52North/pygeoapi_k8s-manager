from dataclasses import dataclass
from datetime import datetime
import json
import logging
from threading import Thread
import time
from typing import (
    Any,
    Optional,
    cast,
)

from pygeoapi.process.manager.base import (
    BaseManager,
    BaseProcessor,
    DATETIME_FORMAT,
    Subscriber,
    RequestedResponse,
)

from pygeoapi.util import (
    JobStatus,
)

from kubernetes import (
    client as k8s_client,
    config as k8s_config,
)

from .util import (
    JobDict,
    current_namespace,
    format_annotation_key,
    format_job_name,
    hide_secret_values,
    is_k8s_job_name,
    job_status_from_k8s,
    now_str,
    parse_annotation_key,
)

LOGGER = logging.getLogger(__name__)

K8S_ANNOTATION_KEY_JOB_START = "job-start-datetime"

class KubernetesProcessor(BaseProcessor):
    @dataclass(frozen=True)
    class JobPodSpec:
        pod_spec: k8s_client.V1PodSpec
        extra_annotations: dict[str, str]
        extra_labels: dict[str, str]

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
        raise NotImplementedError(
            "Kubernetes Processes can't be executed directly, use KubernetesManager"
        )

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
        if manager_def.get('mode') == 'test':
            self.namespace = 'test'
        else:
            try:
                k8s_config.load_kube_config()
            except Exception as e:
                LOGGER.error(e)
                # load_kube_config might throw anything
                k8s_config.load_incluster_config()

            self.namespace = current_namespace()
        # set logging for dependencies
        if manager_def.get('logging'):
            for lib, level in manager_def.get('logging').items():
                LOGGER.debug(f"Set log level '{level}' for library '{lib}")
                logging.getLogger(lib).setLevel(getattr(logging, level.upper(), logging.WARNING))

    def add_job(self, job_metadata):
        # For k8s, add_job is implied by executing the job
        return

    def update_job(self, processid, job_id, update_dict):
        # we could update the metadata by changing the job annotations
        raise NotImplementedError("Currently there's no use case for updating k8s jobs")

    def get_jobs(self, status = None, limit = None, offset = None):
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
                for k8s_job in k8s_client.BatchV1Api().list_namespaced_job(
                    namespace=self.namespace,
                ).items
                if is_k8s_job_name(k8s_job.metadata.name)
            ),
            key=get_start_time_from_job,
            reverse=True,
        )

        number_matched = len(k8s_jobs)

        # NOTE: need to paginate before expensive single job serialization
        if offset:
            k8s_jobs = k8s_jobs[offset:]

        if limit:
            k8s_jobs = k8s_jobs[:limit]

        return {
            "jobs": [
                job_from_k8s(k8s_job, job_message(self.namespace, k8s_job))
                for k8s_job in k8s_jobs
            ],
            "numberMatched": number_matched,
        }

    def _execute_handler_sync(
        self,
        p: BaseProcessor, # EHJ: why BaseProcessor here, if it is passed directly into a
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
        the job status until it the job is finished, vanished, or failed.
        Vanish is a job, if deleted from k8s without interaction of
        this manager.

        :param p: `pygeoapi.t` object
        :param job_id: job identifier
        :param data_dict: `dict` of data parameters

        :returns: tuple of MIME type, response payload and status
        """
        self._execute_handler_async(
            p=p, job_id=job_id, data_dict=data_dict, subscriber=subscriber
        )

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
            job_name = format_job_name(job_id=job_id)
            job_pod_spec = p.create_job_pod_spec(
                data=data_dict,
                job_name=job_name,
            )

            annotations = {
                "identifier": job_id,
                "process_id": p.metadata.get("id"),
                "job_start_datetime": now_str(),
                **job_pod_spec.extra_annotations,
            }

            job = k8s_client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=k8s_client.V1ObjectMeta(
                    name=job_name,
                    annotations={
                        format_annotation_key(k): v for k, v in annotations.items()
                    },
                ),
                spec=k8s_client.V1JobSpec(
                    template=k8s_client.V1PodTemplateSpec(
                        metadata=k8s_client.V1ObjectMeta(labels=job_pod_spec.extra_labels),
                        spec=job_pod_spec.pod_spec,
                    ),
                    backoff_limit=0,
                    # about 3 months
                    ttl_seconds_after_finished=60 * 60 * 24 * 100,
                ),
            )

            self.batch_v1.create_namespaced_job(body=job, namespace=self.namespace)

            LOGGER.info("Add job %s in ns %s", job.metadata.name, self.namespace)

            return ("application/json", {}, JobStatus.accepted)

def get_start_time_from_job(job: k8s_client.V1Job) -> str:
    key = format_annotation_key(K8S_ANNOTATION_KEY_JOB_START)
    return job.metadata.annotations.get(key, "")


def job_message(namespace: str, job: k8s_client.V1Job) -> Optional[str]:
    if job_status_from_k8s(job.status) == JobStatus.accepted:
        # if a job is in state accepted, it means that it can run right now
        # and the events can show why that is
        events: k8s_client.V1EventList = k8s_client.CoreV1Api().list_namespaced_event(
            namespace=namespace,
            field_selector=(
                f"involvedObject.name={job.metadata.name},"
                "involvedObject.kind=Job"
            ),
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


def pod_for_job(namespace: str, job: k8s_client.V1Job) -> Optional[k8s_client.V1Pod]:
    label_selector = ",".join(
        f"{key}={value}" for key, value in job.spec.selector.match_labels.items()
    )
    pods: k8s_client.V1PodList = k8s_client.CoreV1Api().list_namespaced_pod(
        namespace=namespace, label_selector=label_selector
    )

    return next(iter(pods.items), None)


def job_from_k8s(job: k8s_client.V1Job, message: Optional[str]) -> JobDict:
    """
    Converts k8s::job to pygeoapi::job
    """
    # annotations is broken in the k8s library, it's None when it is empty
    annotations = job.metadata.annotations or {}
    metadata_from_annotation = {
        parsed_key: v
        for orig_key, v in annotations.items()
        if (parsed_key := parse_annotation_key(orig_key))
    }

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
    completion_time = get_completion_time(job)
    start_time = get_start_time_from_job(job)
    # default values in case we don't get them from metadata
    default_progress = "100" if status == JobStatus.successful else "1"

    return cast(
        JobDict,
        {
            # need this key in order not to crash, overridden by metadata:
            "identifier": "",
            "process_id": "",
            "job_start_datetime": start_time,
            # NOTE: this is passed as string as compatibility with base manager
            "status": status.value,
            "mimetype": None,  # we don't know this in general
            "message": message if message else "",
            "progress": default_progress,
            "job_end_datetime": (
                completion_time.strftime(DATETIME_FORMAT) if completion_time else None
            ),
            **metadata_from_annotation,
        },
    )


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
