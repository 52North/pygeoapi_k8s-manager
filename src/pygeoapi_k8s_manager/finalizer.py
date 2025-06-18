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
import logging
import os
import uuid
from datetime import datetime
from threading import Thread

import boto3
import boto3.session
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from filelock import FileLock, Timeout
from kubernetes import watch
from kubernetes.client import (
    ApiException,
    BatchV1Api,
    CoreV1Api,
    V1Job,
    V1Pod,
)

from .util import format_log_finalizer, get_logs_for_pod, is_k8s_job_name

LOGGER = logging.getLogger(__name__)


class KubernetesFinalizerController:
    def __init__(self, lockfile: str, namespace: str = "default") -> None:
        self.namespace = namespace
        self.finalizer_id = format_log_finalizer()
        self.lockfile = lockfile
        # it will be killed, if it's the last thread in the application
        self.thread = Thread(
            target=self.controller_loop,
            daemon=True,
        )
        self.is_upload_logs_to_s3 = False
        self.resource_version = None

    def start_watching(self) -> None:
        self.thread.start()
        # no join, the thread runs as daemon independent of
        # the caller, e.g. app server worker process/thread

    def controller_loop(self) -> None:
        LOGGER.debug(f"Try to get the lock of '{self.lockfile}'.")
        lock = FileLock(f"{self.lockfile}.lock", thread_local=False)
        try:
            with lock.acquire(timeout=0):
                LOGGER.debug("Got the lock.")
                self.check_s3_log_upload_variables()

                LOGGER.info(f"Start watching events for jobs in namespace '{self.namespace}'.")
                while True:
                    # get fresh list at start and in case of resyncing
                    if self.resource_version is None:
                        self.refresh_resource_version()

                    while True:
                        try:
                            LOGGER.debug("Start inner loop")
                            watcher = watch.Watch()
                            for event in watcher.stream(
                                BatchV1Api().list_namespaced_job,
                                namespace=self.namespace,
                                resource_version=self.resource_version,
                            ):
                                job = event["object"]
                                event_type = event["type"]
                                LOGGER.debug(f"Event '{event_type}' with object job '{job.metadata.name}' received")
                                if self.has_job_ended(job, event_type):
                                    self.handle_job_ended_event(job)
                                elif event_type == "BOOKMARK":
                                    self.resource_version = job.metadata.resource_version
                            LOGGER.debug("Finished inner watch")

                        except ApiException as e:
                            LOGGER.error("Api Exception received. Resetting resource_version and trigger resyncing.")
                            LOGGER.debug(f"Received: {e}")
                            # FIXME raise or rethrow if 403 forbidden
                            self.resource_version = None
                            break

        except Timeout:
            LOGGER.error("Did not get the lock, hopefully someone else will take care of the finalizer task :-(.")
        LOGGER.info("Finished finalizer thread")

    def has_job_ended(self, job, event_type):
        return (
            event_type == "MODIFIED"
            and is_k8s_job_name(job.metadata.name)
            and self.finalizer_id in (job.spec.template.metadata.finalizers or [])
            and ((job.status.completion_time is not None and job.status.succeeded == 1) or job.status.failed == 1)
        )

    def refresh_resource_version(self, k8s_batch_api: BatchV1Api | None = None):
        LOGGER.debug("Requesting initial/new resource_version")
        if k8s_batch_api is None:
            k8s_batch_api = BatchV1Api()
        jobs = k8s_batch_api.list_namespaced_job(self.namespace)
        self.resource_version = jobs.metadata.resource_version
        LOGGER.debug(f"resource_version received: '{self.resource_version}'.")

    def check_s3_log_upload_variables(self) -> None:
        upload_logs_to_s3 = True
        for key in (
            "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT",
            "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY",
            "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET",
            "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME",
            "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX",
        ):
            value = os.getenv(key=key, default=None)
            if value is None or len(value) == 0:
                LOGGER.error(f"Required environment variable '{key}' not configured correctly: '{value}'")
                upload_logs_to_s3 = False
            elif key == "PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX" and not value.endswith("/"):
                os.environ[key] += "/"
                LOGGER.warning(f"Environment variable '{key}' didn't end with '/', appended: '{os.getenv(key)}'")
        if not upload_logs_to_s3:
            LOGGER.info("Will skip s3 upload to log files because of bad configuration")
        self.is_upload_logs_to_s3 = upload_logs_to_s3

    def handle_job_ended_event(
        self,
        job: V1Job,
        k8s_core_api: CoreV1Api | None = None,
    ) -> None:
        LOGGER.debug(
            f"{'Completed ' if job.status.completion_time else 'Failed'} Job '{job.metadata.name}' with matching finalizer '{self.finalizer_id}'"
        )

        if k8s_core_api is None:
            k8s_core_api = CoreV1Api()

        pods = k8s_core_api.list_namespaced_pod(
            namespace=self.namespace, label_selector=f"job-name={job.metadata.name}"
        )
        LOGGER.debug(f"Found '{len(pods.items)}' pod{'s' if len(pods.items) > 1 else ''} for job '{job.metadata.name}'")
        if len(pods.items) != 1:
            LOGGER.error(f"Could not get pod for job '{job.metadata.name}'")
            # FIXME what to do here? Raise error or log only!?
        pod = pods.items[0]
        logs = get_logs_for_pod(pod, k8s_core_api)
        if logs is None or len(logs) == 0:
            # TODO what todo now? skip removing finalizer? skip uploading
            LOGGER.error(f"Could not retrieve logs for pod '{pod.name}'")
        elif self.is_upload_logs_to_s3:
            self.upload_logs_to_s3(self.get_job_name_from(pod), logs)
        # 4 Remove finalizer entry to allow pod termination
        pod.metadata.finalizers.remove(self.finalizer_id)
        body = {"metadata": {"finalizers": (None if len(pod.metadata.finalizers) == 0 else pod.metadata.finalizers)}}
        LOGGER.debug(
            f"Remove finalizer entry with id '{self.finalizer_id}' from pod '{pod.metadata.name}' in ns '{self.namespace}' to allow deletion: '{body}'"
        )
        # V1Pod, status_code(int), headers(HTTPHeaderDict)
        (patched_pod, status, _) = k8s_core_api.patch_namespaced_pod_with_http_info(
            name=pod.metadata.name, namespace=self.namespace, body=body
        )
        LOGGER.debug(
            f"Removed finalizer from pod '{patched_pod.metadata.name}' with HTTP status '{status}'. Finalizer: '{patched_pod.metadata.finalizers}' (None is good!)"
        )

    def upload_logs_to_s3(self, job_name: str, logs: str, s3: BaseClient | None = None) -> None:
        LOGGER.debug("Upload logs of pod")
        #
        # see https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html#envvars-list-AWS_REQUEST_CHECKSUM_CALCULATION # noqa: E501
        #
        #
        os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
        os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "when_required"
        # 2 Connect to s3 bucket
        if s3 is None:
            s3 = boto3.session.Session().client(
                "s3",
                endpoint_url=os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT"),
                aws_access_key_id=os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY"),
                aws_secret_access_key=os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET"),
            )
        bucket_name = os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME")
        log_file_with_path = self.get_log_file_path(s3, job_name, bucket_name)
        # 3 upload file
        LOGGER.debug("Start writing file")
        s3.put_object(Bucket=bucket_name, Key=log_file_with_path, Body=str(logs).encode("utf-8"))
        LOGGER.info(f"Log data saved to 's3://{s3.meta.endpoint_url}/{bucket_name}/{log_file_with_path}'")

    def get_log_file_path(self, s3: BaseClient, job_name: str, bucket_name: str) -> str:
        path = os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX")
        log_file_with_path = f"{path}{datetime.now().strftime('%Y-%m-%d')}_{job_name}-logs.txt"
        LOGGER.debug(f"Upload target: '{s3.meta.endpoint_url}/{bucket_name}/{log_file_with_path}")
        try:
            s3.head_object(Bucket=bucket_name, Key=log_file_with_path)
            log_file_with_path = f"{log_file_with_path[:-4]}.duplicate.txt"
            LOGGER.debug(
                f"Upload target exists. New target: 's3://{s3.meta.endpoint_url}/{bucket_name}/{log_file_with_path}"
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "404":
                LOGGER.error(
                    f"Checking for object 's3://{s3.meta.endpoint_url}/{bucket_name}/{log_file_with_path}' in\
                          bucket failed: {e}"
                )
                # TODO: How to handle this error
        return log_file_with_path

    def get_job_name_from(self, pod: V1Pod) -> str:
        job_name = None if not pod.metadata.labels else pod.metadata.labels.get("job-name")
        if job_name is None:
            LOGGER.error(f"Job name label not found in pod metadata: '{pod.metadata}'. Using millis of start time.")
            job_name = f"pygeoapi-job-{uuid.UUID(int=int(pod.status.start_time.timestamp()))}"
        return job_name
