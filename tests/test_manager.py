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
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from kubernetes.client import (
    BatchV1Api,
    CoreV1Api,
    CoreV1Event,
    CoreV1EventList,
    V1ContainerState,
    V1ContainerStateTerminated,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1Job,
    V1JobCondition,
    V1JobList,
    V1JobSpec,
    V1JobStatus,
    V1JobTemplateSpec,
    V1LabelSelector,
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1PodStatus,
    V1Toleration,
)
from pygeoapi.process.base import JobNotFoundError, JobResultNotFoundError

from pygeoapi_kubernetes_manager.manager import (
    KubernetesManager,
    KubernetesProcessor,
    check_s3_log_upload_variables,
    get_completion_time,
    get_job_name_from,
    get_log_file_path,
    job_from_k8s,
    job_message,
    kubernetes_finalizer_handle_deletion_event,
)
from pygeoapi_kubernetes_manager.util import format_annotation_key, format_job_name


@pytest.fixture
def manager():
    return KubernetesManager({"name": "test-manager", "mode": "test"})


@pytest.fixture
def process_id():
    return "test-process-id"


@pytest.fixture
def k8s_job_1(process_id):
    return V1Job(
        metadata=V1ObjectMeta(
            name=format_job_name("test-1"),
            annotations={
                format_annotation_key("started"): "2025-01-12T13:39:03.000000Z",
                format_annotation_key("identifier"): "identifier-1",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-12T13:42:03.000000Z"),
        ),
        spec=V1JobSpec(
            selector=V1LabelSelector(match_labels={"test-key-1": "test-value-1"}),
            template=V1JobTemplateSpec(),
        ),
    )


@pytest.fixture
def k8s_job_2(process_id):
    return V1Job(
        metadata=V1ObjectMeta(
            name=format_job_name("test-2"),
            annotations={
                format_annotation_key("started"): "2025-01-19T15:42:01.000000Z",
                format_annotation_key("identifier"): "identifier-2",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-19T15:52:01.000000Z"),
        ),
        spec=V1JobSpec(
            selector=V1LabelSelector(match_labels={"test-key-2": "test-value-2"}),
            template=V1JobTemplateSpec(),
        ),
    )


@pytest.fixture
def k8s_job_3_failed(process_id):
    return V1Job(
        metadata=V1ObjectMeta(
            name=format_job_name("test-3"),
            annotations={
                format_annotation_key("started"): "2025-01-02T15:42:01.000000Z",
                format_annotation_key("identifier"): "identifier-3",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=0,
            failed=1,
            active=0,
            conditions=[
                V1JobCondition(
                    last_transition_time=datetime.datetime.fromisoformat("2025-01-02T15:45:01.000000Z"),
                    type="Failed",
                    status="True",
                ),
                V1JobCondition(
                    last_transition_time=datetime.datetime.fromisoformat("2025-01-02T15:48:01.000000Z"),
                    type="Failed",
                    status="True",
                ),
            ],
        ),
    )


@pytest.fixture
def k8s_job_4_events():
    return V1Job(
        metadata=V1ObjectMeta(
            name=format_job_name("test-4"),
            annotations={
                format_annotation_key("job-start-datetime"): "2025-01-19T15:42:01.000000Z",
                format_annotation_key("identifier"): "identifier-4",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=0,
            failed=0,
            active=0,
            completion_time=datetime.datetime.now(datetime.UTC),
        ),
    )


@pytest.fixture
def k8s_job_list(k8s_job_1, k8s_job_2):
    return V1JobList(items=[k8s_job_1, k8s_job_2])


@pytest.fixture
def k8s_pod_list():
    return V1PodList(items=[V1Pod(status=V1PodStatus())])


def test_manager_get_jobs(manager, k8s_job_list, k8s_pod_list, process_id):
    with (
        patch.object(BatchV1Api, "list_namespaced_job", return_value=k8s_job_list),
        patch.object(CoreV1Api, "list_namespaced_pod", return_value=k8s_pod_list),
    ):
        jobs = manager.get_jobs()

    assert jobs is not None
    assert jobs["numberMatched"] == 2
    assert len(jobs["jobs"]) == 2
    # The jobs are ordered in reverse by completion time by get_jobs()
    # test job #1
    job_1 = jobs["jobs"][0]
    assert job_1["started"] == "2025-01-19T15:42:01.000000Z"
    assert job_1["created"] == "2025-01-19T15:42:01.000000Z"
    assert job_1["progress"] == "100"
    assert job_1["status"] == "successful"
    assert job_1["identifier"] == "identifier-2"
    assert job_1["process_id"] == process_id
    assert job_1["finished"] == "2025-01-19T15:52:01.000000Z"
    assert job_1["updated"] == job_1["finished"]
    assert job_1["mimetype"] == "application/json"

    # test job #2
    job_2 = jobs["jobs"][1]
    assert job_2["created"] == "2025-01-12T13:39:03.000000Z"
    assert job_2["started"] == "2025-01-12T13:39:03.000000Z"
    assert job_2["progress"] == "100"
    assert job_2["status"] == "successful"
    assert job_2["identifier"] == "identifier-1"
    assert job_2["process_id"] == process_id
    assert job_2["finished"] == "2025-01-12T13:42:03.000000Z"
    assert job_2["updated"] == job_2["finished"]
    assert job_2["mimetype"] == "application/json"


def test_manager_get_jobs_offset(manager, k8s_job_list, k8s_pod_list, process_id):
    with (
        patch.object(BatchV1Api, "list_namespaced_job", return_value=k8s_job_list),
        patch.object(CoreV1Api, "list_namespaced_pod", return_value=k8s_pod_list),
    ):
        jobs = manager.get_jobs(offset=1)

    assert jobs is not None
    assert jobs["numberMatched"] == 2
    assert len(jobs["jobs"]) == 1
    # The jobs are ordered in reverse by completion time by get_jobs()
    # test job #1, which is #2 from the fixture
    job_1 = jobs["jobs"][0]
    assert job_1["created"] == "2025-01-12T13:39:03.000000Z"
    assert job_1["started"] == "2025-01-12T13:39:03.000000Z"
    assert job_1["progress"] == "100"
    assert job_1["status"] == "successful"
    assert job_1["identifier"] == "identifier-1"
    assert job_1["process_id"] == process_id
    assert job_1["finished"] == "2025-01-12T13:42:03.000000Z"
    assert job_1["updated"] == job_1["finished"]
    assert job_1["mimetype"] == "application/json"


def test_manager_get_jobs_limit(manager, k8s_job_list, k8s_pod_list, process_id):
    with (
        patch.object(BatchV1Api, "list_namespaced_job", return_value=k8s_job_list),
        patch.object(CoreV1Api, "list_namespaced_pod", return_value=k8s_pod_list),
    ):
        jobs = manager.get_jobs(limit=1)

    assert jobs is not None
    assert jobs["numberMatched"] == 2
    assert len(jobs["jobs"]) == 1
    # The jobs are ordered in reverse by completion time by get_jobs()
    # test job #1, which is #1 from the fixture
    job_1 = jobs["jobs"][0]
    assert job_1["started"] == "2025-01-19T15:42:01.000000Z"
    assert job_1["progress"] == "100"
    assert job_1["status"] == "successful"
    assert job_1["identifier"] == "identifier-2"
    assert job_1["process_id"] == process_id
    assert job_1["finished"] == "2025-01-19T15:52:01.000000Z"
    assert job_1["updated"] == job_1["finished"]
    assert job_1["mimetype"] == "application/json"


def test_manager_get_job_result_raises_error_on_no_job_returned(manager, process_id):
    with pytest.raises(JobNotFoundError) as error:
        with patch.object(KubernetesManager, "get_job", return_value=None):
            manager.get_job_result(process_id)
    assert error.type is JobNotFoundError
    assert error.match(f"No job with id '{process_id}' found!")


def test_manager_get_job_result_raises_error_on_failed_job(manager, process_id):
    state = "failed"
    with pytest.raises(JobResultNotFoundError) as error:
        with patch.object(
            KubernetesManager,
            "get_job",
            return_value={"identifier": process_id, "status": state},
        ):
            manager.get_job_result(process_id)
    assert error.type is JobResultNotFoundError
    assert error.match(f"No results for job '{process_id}' with state '{state}' found.")


def test_manager_get_job_result_raises_error_on_absent_pod(manager, process_id):
    with pytest.raises(JobResultNotFoundError) as error:
        with (
            patch.object(
                KubernetesManager,
                "get_job",
                return_value={"identifier": process_id, "status": "successful"},
            ),
            patch("pygeoapi_kubernetes_manager.manager.pod_for_job_id", return_value=None),
        ):
            manager.get_job_result(process_id)
    assert error.type is JobResultNotFoundError
    assert error.match(f"Pod not found for job '{process_id}'")


@pytest.fixture
def mocked_pod():
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.namespace = "test-namespace"
    pod.spec.containers = [MagicMock(name="container-1")]
    return pod


def test_manager_get_job_result_raises_error_on_absent_logs(manager, process_id, mocked_pod):
    with pytest.raises(JobResultNotFoundError) as error:
        with (
            patch.object(
                KubernetesManager,
                "get_job",
                return_value={"identifier": process_id, "status": "successful"},
            ),
            patch(
                "pygeoapi_kubernetes_manager.manager.pod_for_job_id",
                return_value=mocked_pod,
            ),
            patch.object(CoreV1Api, "read_namespaced_pod_log", return_value=None),
        ):
            manager.get_job_result(process_id)
    assert error.type is JobResultNotFoundError
    assert error.match(f"Could not retrieve logs for job '{process_id}'")


def test_manager_get_job_result_logs(manager, process_id, mocked_pod):
    logs_expected = "test log string"
    with (
        patch.object(
            KubernetesManager,
            "get_job",
            return_value={"identifier": process_id, "status": "successful"},
        ),
        patch(
            "pygeoapi_kubernetes_manager.manager.pod_for_job_id",
            return_value=mocked_pod,
        ),
        patch.object(CoreV1Api, "read_namespaced_pod_log", return_value=logs_expected),
    ):
        mimetype, logs_received = manager.get_job_result(process_id)
    assert mimetype is None
    assert logs_received == logs_expected


def test_manager_adds_tolerations_if_configured(manager):
    tolerations = KubernetesProcessor(
        {
            "name": "tolerations-test-process",
            "tolerations": [
                {"key": "toleration-key", "value": "toleration-value", "operator": "Equal", "effect": "NoSchedule"}
            ],
        },
        {},
    )._add_tolerations()

    assert len(tolerations) == 1
    assert type(tolerations) is dict
    assert len(tolerations["tolerations"]) == 1
    assert type(tolerations["tolerations"]) is list
    assert type(tolerations["tolerations"][0]) is V1Toleration
    toleration = tolerations["tolerations"][0]
    assert toleration.key == "toleration-key"
    assert toleration.value == "toleration-value"
    assert toleration.operator == "Equal"
    assert toleration.effect == "NoSchedule"


def test_manager_does_not_add_tolerations_if_not_configured(manager):
    tolerations = KubernetesProcessor(
        {
            "name": "tolerations-test-process",
        },
        {},
    )._add_tolerations()

    assert tolerations is None


def test_get_completion_time_failed_job(k8s_job_3_failed):
    assert get_completion_time(k8s_job_3_failed) == datetime.datetime.fromisoformat("2025-01-02T15:48:01.000000Z")


@pytest.fixture
def k8s_event_list(k8s_job_4_events):
    return CoreV1EventList(
        items=[
            CoreV1Event(
                involved_object=object(),
                metadata=object(),
                message="first event",
            ),
            CoreV1Event(involved_object=object(), metadata=object(), message="last event"),
        ]
    )


def test_job_message_from_events_from_accepted_job(k8s_job_4_events, k8s_event_list):
    with patch.object(CoreV1Api, "list_namespaced_event", return_value=k8s_event_list):
        assert job_message("test", k8s_job_4_events) == "last event"


@pytest.fixture
def k8s_pod_with_container_stati():
    return V1Pod(
        status=V1PodStatus(
            container_statuses=[
                V1ContainerStatus(
                    name=object(),
                    image_id=object(),
                    image=object(),
                    ready=object(),
                    restart_count=0,
                    state=V1ContainerState(
                        waiting=V1ContainerStateWaiting(
                            reason="test-waiting-reason",
                            message="test-waiting-message",
                        )
                    ),
                ),
                V1ContainerStatus(
                    name=object(),
                    image_id=object(),
                    image=object(),
                    ready=object(),
                    restart_count=0,
                    state=V1ContainerState(
                        terminated=V1ContainerStateTerminated(
                            reason="test-terminated-reason",
                            message="test-terminated-message",
                            exit_code=0,
                        )
                    ),
                ),
            ]
        )
    )


def test_job_message_from_pod_container_stati(k8s_pod_with_container_stati, k8s_job_1):
    with patch.object(
        CoreV1Api,
        "list_namespaced_pod",
        return_value=V1PodList(items=[k8s_pod_with_container_stati]),
    ):
        assert job_message("test", k8s_job_1) == "test-waiting-reason: test-waiting-message"


def test_add_job_returns_only(manager):
    assert manager.add_job({}) is None


def test_update_job_returns_not_implemented_error(manager):
    with pytest.raises(NotImplementedError) as error:
        manager.update_job(object(), object(), object())
    assert error.type is NotImplementedError
    assert error.match("Currently there's no use case for updating k8s jobs")


@pytest.mark.skip("TODO implement")
def test_execute_job(manager, process_id):
    # TODO: Continue work here
    raise AssertionError("TODO implement")


@pytest.fixture
def manager_with_log_level():
    return KubernetesManager(
        {
            "name": "test-manager",
            "mode": "test",
            "logging": {"kubernetes": "INFO", "boto3": "CRITICAL"},
        }
    )


def test_manager_log_level_configuration(manager_with_log_level):
    manager_with_log_level  # noqa: B018
    assert logging.getLogger("kubernetes").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("boto3").getEffectiveLevel() == logging.CRITICAL


@pytest.fixture
def k8s_job_without_mimetype_annotation(process_id):
    return V1Job(
        metadata=V1ObjectMeta(
            name=format_job_name("test-2"),
            annotations={
                format_annotation_key("started"): "2025-01-19T15:42:01.000000Z",
                format_annotation_key("identifier"): "identifier-2",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-19T15:52:01.000000Z"),
        ),
        spec=V1JobSpec(
            selector=V1LabelSelector(match_labels={"test-key-2": "test-value-2"}),
            template=V1JobTemplateSpec(),
        ),
    )


def test_job_get_default_mimetype_if_annotation_is_missing(
    k8s_job_without_mimetype_annotation,
):
    job = job_from_k8s(k8s_job_without_mimetype_annotation, "test-message")

    assert job["mimetype"] == "application/json"


def test_kubernetes_processor_sets_mimetype():
    processor = KubernetesProcessor(process_metadata={}, processor_def={"name": "test-name"})

    assert processor.mimetype == "application/json"


def test_manager_starts_no_thread_if_not_configured(manager):
    with pytest.raises(AttributeError) as error:
        manager.finalizer_controller  # noqa: B018

    assert error.type is AttributeError
    assert error.match("'KubernetesManager' object has no attribute 'finalizer_controller'")


def test_check_s3_log_upload_variables():
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT", None)
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"] = "configured"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = "configured"
    assert check_s3_log_upload_variables() is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY", None)
    assert check_s3_log_upload_variables() is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET", None)
    assert check_s3_log_upload_variables() is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME", None)
    assert check_s3_log_upload_variables() is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME"] = "configured"
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX", None)
    assert check_s3_log_upload_variables() is False

    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = "configured"
    assert check_s3_log_upload_variables() is True

    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME", None)
    os.environ.pop("PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX", None)


def test_kubernetes_finalizer_handle_deletion_event_does_nothing_if_not_required():
    k8s_core_api = MagicMock()
    test_pod = MagicMock()
    test_pod.metadata.name = "test-pod"
    test_pod.metadata.finalizers = ["not-my-finalizer"]

    kubernetes_finalizer_handle_deletion_event(
        k8s_core_api=k8s_core_api,
        finalizer_id="test_finalizer_id",
        namespace="test_namespace",
        pod=test_pod,
        upload_logs=False,
    )

    k8s_core_api.read_namespaced_pod_log_with_http_info.assert_not_called()


def test_kubernetes_finalizer_handle_deletion_event_removes_finalizer_if_no_logs_found():
    k8s_core_api = MagicMock()
    k8s_core_api.read_namespaced_pod_log_with_http_info.return_value = None
    deleted_pod = MagicMock()
    deleted_pod.metadata.name = "deleted-pod"
    k8s_core_api.patch_namespaced_pod_with_http_info.return_value = (
        deleted_pod,
        200,
    )
    finalizer_id = "test_finalizer_id"
    test_pod = MagicMock()
    test_pod.metadata.name = "test-pod"
    test_pod.metadata.finalizers = ["not-my-finalizer", finalizer_id]

    with patch("pygeoapi_kubernetes_manager.manager.upload_logs_to_s3") as mocked_upload_logs_to_s3:
        kubernetes_finalizer_handle_deletion_event(
            k8s_core_api=k8s_core_api,
            finalizer_id=finalizer_id,
            namespace="test_namespace",
            pod=test_pod,
            upload_logs=False,
        )

        k8s_core_api.read_namespaced_pod_log_with_http_info.assert_called_once()
        mocked_upload_logs_to_s3.assert_not_called()
        k8s_core_api.patch_namespaced_pod_with_http_info.assert_called_once()
        assert test_pod.metadata.finalizers == ["not-my-finalizer"]


@pytest.fixture()
def pod_with_job_name() -> V1Pod:
    return V1Pod(metadata=V1ObjectMeta(labels={"job-name": "test-job-name"}))


def test_get_job_name_from_pod(pod_with_job_name):
    assert get_job_name_from(pod_with_job_name) == "test-job-name"


def test_get_job_name_returns_alternative_job_name():
    test_pod = V1Pod(
        metadata=V1ObjectMeta(),
        status=V1PodStatus(start_time=datetime.datetime(1970, 1, 1, 12, 00, 0, tzinfo=datetime.timezone.utc)),
    )
    assert get_job_name_from(test_pod) == "pygeoapi-job-00000000-0000-0000-0000-00000000a8c0"


def test_get_log_file_path(pod_with_job_name):
    test_endpoint_url = "test-endpoint-url"
    test_bucket_prefix = "my-bucket/prefix/"
    os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"] = test_bucket_prefix
    s3 = MagicMock()
    s3.meta.endpoint_url = test_endpoint_url
    error_response = {
        "Error": {
            "Code": "404",
        }
    }
    s3.head_object.side_effect = ClientError(error_response, "test-operations-name")
    log_file_path = get_log_file_path(s3, pod_with_job_name, "test-bucket-name")

    assert log_file_path == f"{test_bucket_prefix}test-job-name-logs.txt"

    s3.head_object.result_value = None
    s3.head_object.side_effect = None
    log_file_path = get_log_file_path(s3, pod_with_job_name, "test-bucket-name")

    assert log_file_path == f"{test_bucket_prefix}test-job-name-logs.duplicate.txt"

    del os.environ["PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX"]


@pytest.fixture
def manager_with_finalizer():
    return KubernetesManager({"name": "test-manager", "mode": "test", "finalizer_controller": True})


@pytest.mark.skip("Causing to much logging noise atm")
def test_manager_starts_thread_if_finalizer_is_configured(manager_with_finalizer):
    assert manager_with_finalizer.finalizer_controller.is_alive()
    manager_with_finalizer.finalizer_controller.do_run = False


@pytest.mark.skip("TODO implement")
def test_kubernetes_finalizer_loop():
    raise AssertionError("Implement me")
