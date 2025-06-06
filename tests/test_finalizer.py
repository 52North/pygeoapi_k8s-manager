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
import os
from unittest.mock import MagicMock, patch

import pytest
from boto3.session import Session
from botocore.exceptions import ClientError
from kubernetes.client import (
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1PodStatus,
)

from pygeoapi_kubernetes_manager.finalizer import KubernetesFinalizerController
from pygeoapi_kubernetes_manager.util import format_log_finalizer


@pytest.fixture()
def finalizer():
    return KubernetesFinalizerController("")


def test_check_s3_log_upload_variables(finalizer):
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT", None)
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = "configured"
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY", None)
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET", None)
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME", None)
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX", None)
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = "configured"
    finalizer.check_s3_log_upload_variables()
    assert finalizer.is_upload_logs_to_s3 is True

    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX", None)


def test_kubernetes_finalizer_handle_job_ended_event_removes_finalizer_if_no_logs_found(finalizer):
    k8s_core_api = MagicMock()
    k8s_core_api.read_namespaced_pod_log.return_value = None
    patched_pod = MagicMock()
    patched_pod.metadata.name = "deleted-pod"
    k8s_core_api.patch_namespaced_pod_with_http_info.return_value = (
        patched_pod,
        200,
        {},
    )
    test_job = MagicMock()
    test_job.metadata.name = "test-job"
    test_pod = MagicMock()
    test_pod.metadata.name = "test-pod"
    test_pod.metadata.finalizers = ["not-my-finalizer", format_log_finalizer()]
    k8s_core_api.list_namespaced_pod.return_value = V1PodList(items=[test_pod])
    finalizer.is_upload_logs_to_s3 = False

    with patch(
        "pygeoapi_kubernetes_manager.finalizer.KubernetesFinalizerController.upload_logs_to_s3"
    ) as mocked_upload_logs_to_s3:
        finalizer.handle_job_ended_event(
            k8s_core_api=k8s_core_api,
            job=test_job,
        )

        k8s_core_api.read_namespaced_pod_log.assert_called_once()
        mocked_upload_logs_to_s3.assert_not_called()
        k8s_core_api.patch_namespaced_pod_with_http_info.assert_called_once()
        assert test_pod.metadata.finalizers == ["not-my-finalizer"]


@pytest.fixture()
def pod_with_job_name() -> V1Pod:
    return V1Pod(metadata=V1ObjectMeta(labels={"job-name": "test-job-name"}))


def test_get_job_name_from_pod(finalizer, pod_with_job_name):
    assert finalizer.get_job_name_from(pod_with_job_name) == "test-job-name"


def test_get_job_name_returns_alternative_job_name(finalizer):
    test_pod = V1Pod(
        metadata=V1ObjectMeta(),
        status=V1PodStatus(start_time=datetime.datetime(1970, 1, 1, 12, 00, 0, tzinfo=datetime.timezone.utc)),
    )
    assert finalizer.get_job_name_from(test_pod) == "pygeoapi-job-00000000-0000-0000-0000-00000000a8c0"


@pytest.fixture()
def s3_endpoint_url():
    return "test-endpoint-url"


@pytest.fixture()
def s3_mock(s3_endpoint_url):
    s3 = MagicMock()
    s3.meta.endpoint_url = s3_endpoint_url
    error_response = {
        "Error": {
            "Code": "404",
        }
    }
    s3.head_object.side_effect = ClientError(error_response, "test-operations-name")
    return s3


def test_get_log_file_path(finalizer, s3_mock):
    test_bucket_prefix = "my-bucket/prefix/"
    test_job_name = "test-job-name"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = test_bucket_prefix
    log_file_path = finalizer.get_log_file_path(s3_mock, test_job_name, "test-bucket-name")

    assert log_file_path == f"{test_bucket_prefix}{datetime.datetime.now().strftime('%Y-%m-%d')}_test-job-name-logs.txt"

    s3_mock.head_object.result_value = None
    s3_mock.head_object.side_effect = None
    log_file_path = finalizer.get_log_file_path(s3_mock, test_job_name, "test-bucket-name")

    assert (
        log_file_path
        == f"{test_bucket_prefix}{datetime.datetime.now().strftime('%Y-%m-%d')}_test-job-name-logs.duplicate.txt"
    )

    del os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"]


def test_upload_logs_to_s3(finalizer, pod_with_job_name, s3_mock):
    test_bucket_prefix = "my-bucket/prefix/"
    test_bucket_name = "my-test-bucket-name"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = test_bucket_prefix
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"] = test_bucket_name

    test_log_data = "test-logs-string"

    with patch.object(Session, "client", return_value=s3_mock):
        finalizer.upload_logs_to_s3(finalizer.get_job_name_from(pod_with_job_name), test_log_data)

    s3_mock.put_object.assert_called_once_with(
        Bucket=test_bucket_name,
        Key=f"{test_bucket_prefix}{datetime.datetime.now().strftime('%Y-%m-%d')}_{finalizer.get_job_name_from(pod_with_job_name)}-logs.txt",
        Body=test_log_data.encode("utf-8"),
    )

    del os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"]
    del os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"]


def test_refresh_resource_version(finalizer):
    jobs_list = MagicMock()
    jobs_list.metadata.resource_version = "my-resource-version"
    k8s_batch_api = MagicMock()
    k8s_batch_api.list_namespaced_job.return_value = jobs_list

    finalizer.refresh_resource_version(k8s_batch_api)
    assert finalizer.resource_version == "my-resource-version"


def test_has_job_ended(finalizer):
    # wrong event types
    for ignored_event_type in ["ADDED", "DELETED"]:
        assert finalizer.has_job_ended(None, ignored_event_type) is False
    # wrong jobs
    wrong_job = MagicMock()
    for ignored_job_name in ["pygeoapi", "job", "failing"]:
        wrong_job.metadata.name = ignored_job_name
        assert finalizer.has_job_ended(wrong_job, "MODIFIED") is False
    # wrong finalizer
    wrong_job.metadata.name = "pygeoapi-job-test"
    wrong_job.spec.template.metadata.finalizers = ["wrong-finalizer-1", "wrong-finalizer-2"]
    assert finalizer.has_job_ended(wrong_job, "MODIFIED") is False
    # not ended
    wrong_job.spec.template.metadata.finalizers = [format_log_finalizer()]
    wrong_job.status.completion_time = None
    assert finalizer.has_job_ended(wrong_job, "MODIFIED") is False
    # ended jobs
    ended_job = wrong_job
    ended_job.status.completion_time = datetime.datetime.now()
    ended_job.status.succeeded = 1
    assert finalizer.has_job_ended(ended_job, "MODIFIED")
    ended_job.status.completion_time = None
    ended_job.status.failed = 1
    assert finalizer.has_job_ended(ended_job, "MODIFIED")
