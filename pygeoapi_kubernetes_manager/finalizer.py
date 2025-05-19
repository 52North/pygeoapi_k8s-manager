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
from threading import Thread

import boto3
import boto3.session
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from filelock import FileLock, Timeout
from kubernetes import (
    client as k8s_client,
)
from kubernetes import watch
from kubernetes.client import (
    CoreV1Api,
    V1Pod,
)

from .util import format_log_finalizer, is_k8s_job_name

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
                # check env config
                self.check_s3_log_upload_variables()

                k8s_core_api = k8s_client.CoreV1Api()

                resource_version = None

                LOGGER.info(f"Start watching events for pods in namespace '{self.namespace}'.")
                while True:
                    # get fresh list at start and in case of resyncing
                    if resource_version is None:
                        LOGGER.debug("Requesting initial/new resource_version")
                        pods = k8s_core_api.list_namespaced_pod(self.namespace)
                        resource_version = pods.metadata.resource_version
                        LOGGER.debug(f"resource_version received: '{resource_version}'.")

                    while True:
                        try:
                            LOGGER.debug("Start inner watch")
                            watcher = watch.Watch()
                            for event in watcher.stream(
                                k8s_core_api.list_namespaced_pod,
                                namespace=self.namespace,
                                resource_version=resource_version,
                            ):
                                pod = event["object"]
                                event_type = event["type"]
                                LOGGER.debug(f"Event '{event_type}' with object pod '{pod.metadata.name}' received")

                                # TODO maybe, switch to match statement!?
                                if (
                                    event_type in ("ADDED", "MODIFIED")
                                    and pod.metadata.deletion_timestamp is None
                                    and is_k8s_job_name(pod.metadata.name)
                                    and self.finalizer_id not in (pod.metadata.finalizers or [])
                                ):
                                    self.add_finalizer_to_pod_metadata(
                                        k8s_core_api,
                                        pod,
                                    )
                                elif (
                                    event_type in ("MODIFIED", "DELETED")
                                    and pod.metadata.deletion_timestamp
                                    and is_k8s_job_name(pod.metadata.name)
                                    and self.finalizer_id in (pod.metadata.finalizers or [])
                                ):
                                    self.handle_deletion_event(
                                        k8s_core_api,
                                        pod,
                                    )
                                elif event_type == "BOOKMARK":
                                    LOGGER.debug(
                                        f"Processing 'Bookmark': resource version: \
                                            '{resource_version}' -> {pod.metadata.resource_version}'."
                                    )
                                    resource_version = pod.metadata.resource_version
                            LOGGER.debug("Finished inner watch")

                        except k8s_client.ApiException:
                            LOGGER.debug("Api Exception received. Resetting resource_version and trigger resyncing.")
                            resource_version = None
                            break

        except Timeout:
            LOGGER.error("Did not get the lock, hopefully someone else will take care of the finalizer task :-(.")
        LOGGER.info("Finished finalizer thread")

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
        if not upload_logs_to_s3:
            LOGGER.info("Will skip s3 upload to log files because of bad configuration")
        self.is_upload_logs_to_s3 = upload_logs_to_s3

    def add_finalizer_to_pod_metadata(self, k8s_core_api: CoreV1Api, finalizer_id: str, pod: V1Pod) -> None:
        LOGGER.debug(f"Found pod added '{pod.metadata.name}' without matching finalizer '{finalizer_id}'.")
        if pod.metadata.finalizers is None:
            pod.metadata.finalizers = []
        pod.metadata.finalizers.append(finalizer_id)
        body = {"metadata": {"finalizers": (None if len(pod.metadata.finalizers) == 0 else pod.metadata.finalizers)}}
        (
            updated_pod,
            status,
        ) = k8s_core_api.patch_namespaced_pod_with_http_info(
            name=pod.metadata.name, namespace=self.namespace, body=body
        )
        LOGGER.debug(f"Added finalizer to pod '{updated_pod.metadata.name}' with HTTP status '{status}'")

    def handle_deletion_event(
        self,
        k8s_core_api: CoreV1Api,
        pod: V1Pod,
    ) -> None:
        LOGGER.debug(
            f"Found pod '{pod.metadata.name}' to be deleted since \
                '{pod.metadata.deletion_timestamp}' with matching finalizer '{self.finalizer_id}'."
        )
        if self.finalizer_id not in pod.metadata.finalizers:
            return

        # 1 get logs from pod container #1
        logs = k8s_core_api.read_namespaced_pod_log(
            name=pod.metadata.name,
            namespace=pod.metadata.namespace,
            container=pod.spec.containers[0].name,
        )
        if logs is None or len(logs) == 0:
            # TODO what todo now? skip removing finalizer? skip uploading
            LOGGER.error(f"Could not retrieve logs for pod '{pod.name}'")
        elif self.is_upload_logs_to_s3:
            self.upload_logs_to_s3(self.get_job_name_from(pod), logs)
        # 4 Remove finalizer entry to allow pod termination
        pod.metadata.finalizers.remove(self.finalizer_id)
        body = {"metadata": {"finalizers": (None if len(pod.metadata.finalizers) == 0 else pod.metadata.finalizers)}}
        # V1Pod, status_code(int), headers(HTTPHeaderDict)
        (
            deleted_pod,
            status,
        ) = k8s_core_api.patch_namespaced_pod_with_http_info(
            name=pod.metadata.name, namespace=self.namespace, body=body
        )
        LOGGER.debug(f"Removed finalizer from pod '{deleted_pod.metadata.name}' with HTTP status '{status}'")

    def upload_logs_to_s3(
        self,
        job_name: str,
        logs: str,
    ) -> None:
        LOGGER.debug("Retrieve logs from pod")
        #
        # see https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html#envvars-list-AWS_REQUEST_CHECKSUM_CALCULATION # noqa: E501
        #
        #
        os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
        os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "when_required"
        # 2 Connect to s3 bucket
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
        LOGGER.info(f"Log data saved to '{log_file_with_path}'")

    def get_log_file_path(self, s3: BaseClient, job_name: str, bucket_name: str) -> str:
        path = os.getenv("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX")
        log_file_with_path = f"{path}{job_name}-logs.txt"
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
