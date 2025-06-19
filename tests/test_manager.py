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
from uuid import UUID

import pytest
import time_machine
from kubernetes.client import (
    BatchV1Api,
    CoreV1Api,
    CoreV1Event,
    CoreV1EventList,
    V1Container,
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
    V1PodSpec,
    V1PodStatus,
    V1Toleration,
)
from pygeoapi.process.base import BaseProcessor, JobNotFoundError, JobResultNotFoundError, ProcessorExecuteError

from pygeoapi_k8s_manager.manager import (
    KubernetesManager,
    KubernetesProcessor,
    add_job_id_env,
    create_job_body,
    get_completion_time,
    job_from_k8s,
    job_message,
)
from pygeoapi_k8s_manager.util import format_annotation_key, format_job_name, format_log_finalizer


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
                format_annotation_key("started"): "2025-01-12T13:39:03+00:00",
                format_annotation_key("identifier"): "identifier-1",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-12T13:42:03+00:00"),
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
                format_annotation_key("started"): "2025-01-19T15:42:01+00:00",
                format_annotation_key("identifier"): "identifier-2",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-19T15:52:01+00:00"),
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
                format_annotation_key("started"): "2025-01-02T15:42:01+00:00",
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
                    last_transition_time=datetime.datetime.fromisoformat("2025-01-02T15:45:01+00:00"),
                    type="Failed",
                    status="True",
                ),
                V1JobCondition(
                    last_transition_time=datetime.datetime.fromisoformat("2025-01-02T15:48:01+00:00"),
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
                format_annotation_key("job-start-datetime"): "2025-01-19T15:42:01+00:00",
                format_annotation_key("identifier"): "identifier-4",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=0,
            failed=0,
            active=0,
            completion_time=datetime.datetime.now(tz=datetime.timezone.utc),
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
    assert job_1["started"] == "2025-01-19T15:42:01+00:00"
    assert job_1["created"] == "2025-01-19T15:42:01+00:00"
    assert job_1["progress"] == "100"
    assert job_1["status"] == "successful"
    assert job_1["identifier"] == "identifier-2"
    assert job_1["process_id"] == process_id
    assert job_1["finished"] == "2025-01-19T15:52:01.000000Z"
    assert job_1["updated"] == job_1["finished"]
    assert job_1["mimetype"] == "application/json"

    # test job #2
    job_2 = jobs["jobs"][1]
    assert job_2["created"] == "2025-01-12T13:39:03+00:00"
    assert job_2["started"] == "2025-01-12T13:39:03+00:00"
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
    assert job_1["created"] == "2025-01-12T13:39:03+00:00"
    assert job_1["started"] == "2025-01-12T13:39:03+00:00"
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
    assert job_1["started"] == "2025-01-19T15:42:01+00:00"
    assert job_1["progress"] == "100"
    assert job_1["status"] == "successful"
    assert job_1["identifier"] == "identifier-2"
    assert job_1["process_id"] == process_id
    assert job_1["finished"] == "2025-01-19T15:52:01.000000Z"
    assert job_1["updated"] == job_1["finished"]
    assert job_1["mimetype"] == "application/json"


def test_manager_get_job_result_raises_error_on_no_job_returned(manager, process_id):
    with pytest.raises(JobNotFoundError) as error:
        with patch.object(
            KubernetesManager, "get_k8s_job", side_effect=JobNotFoundError(f"No job with id '{process_id}' found!")
        ):
            manager.get_job_result(process_id)
    assert error.type is JobNotFoundError
    assert error.match(f"No job with id '{process_id}' found!")


def test_manager_get_job_result_raises_error_on_failed_job(manager, process_id):
    state = "failed"
    with (
        pytest.raises(JobResultNotFoundError) as error,
        patch.object(
            KubernetesManager,
            "get_k8s_job",
            return_value=None,
        ),
        patch(
            "pygeoapi_k8s_manager.manager.job_from_k8s",
            return_value={"identifier": process_id, "status": state},
        ),
        patch("pygeoapi_k8s_manager.manager.job_message", return_value=None),
    ):
        manager.get_job_result(process_id)
    assert error.type is JobResultNotFoundError
    assert error.match(f"No results for job '{process_id}' with state '{state}' found.")


@pytest.fixture
def mocked_pod():
    container = MagicMock()
    container.name = "container-1"
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.namespace = "test-namespace"
    pod.spec.containers = [container]
    return pod


def test_manager_get_job_result(manager, process_id, mocked_pod):
    test_mimetype = "application/pygeoapi-testing-mimetype"
    test_result = "my test result string"
    job = {"status": "successful"}
    k8s_job = MagicMock()
    k8s_job.metadata.annotations = {
        format_annotation_key("result-mimetype"): test_mimetype,
        format_annotation_key("result-value"): test_result,
    }
    with (
        patch.object(
            KubernetesManager,
            "get_k8s_job",
            return_value=k8s_job,
        ),
        patch("pygeoapi_k8s_manager.manager.job_message", return_value=None),
        patch(
            "pygeoapi_k8s_manager.manager.job_from_k8s",
            return_value=job,
        ),
    ):
        mimetype, result = manager.get_job_result(process_id)
    assert mimetype == test_mimetype
    assert result == test_result


@pytest.fixture()
def minimal_job_spec():
    return KubernetesProcessor.JobPodSpec(V1PodSpec(containers=[V1Container(name="test-container-name")]), {})


@pytest.fixture()
def toleration():
    return {"key": "toleration-key", "value": "toleration-value", "operator": "Equal", "effect": "NoSchedule"}


def test_manager_adds_tolerations_if_configured(minimal_job_spec, toleration):
    spec_with_tolerations = KubernetesProcessor(
        {
            "name": "tolerations-test-process",
            "tolerations": [toleration],
        },
        {},
    )._add_tolerations(minimal_job_spec)

    tolerations = spec_with_tolerations.pod_spec.tolerations
    assert len(tolerations) == 1
    assert type(tolerations) is list
    assert len(tolerations) == 1
    assert type(tolerations[0]) is V1Toleration
    assert tolerations[0].key == "toleration-key"
    assert tolerations[0].value == "toleration-value"
    assert tolerations[0].operator == "Equal"
    assert tolerations[0].effect == "NoSchedule"


def test_manager_does_not_add_tolerations_if_not_configured(minimal_job_spec):
    spec_without_tolerations = KubernetesProcessor(
        {
            "name": "tolerations-test-process",
        },
        {},
    )._add_tolerations(minimal_job_spec)

    assert spec_without_tolerations.pod_spec.tolerations is None


def test_get_completion_time_failed_job(k8s_job_3_failed):
    assert get_completion_time(k8s_job_3_failed) == datetime.datetime.fromisoformat("2025-01-02T15:48:01+00:00")


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
                format_annotation_key("started"): "2025-01-19T15:42:01+00:00",
                format_annotation_key("identifier"): "identifier-2",
                format_annotation_key("process_id"): process_id,
            },
        ),
        status=V1JobStatus(
            succeeded=1,
            completion_time=datetime.datetime.fromisoformat("2025-01-19T15:52:01+00:00"),
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
    assert manager.finalizer_controller is None


@pytest.fixture
def manager_with_finalizer():
    return KubernetesManager({"name": "test-manager", "mode": "test", "finalizer_controller": True})


@pytest.fixture()
def job_id():
    return str(UUID(int=52))


@pytest.fixture()
def mimetype():
    return "application/python-test"


@pytest.fixture()
def mocked_processor(minimal_job_spec, mimetype, process_id):
    p = MagicMock()
    p.create_job_pod_spec.return_value = minimal_job_spec
    p.metadata = {"id": process_id}
    p.mimetype = mimetype
    return p


def test_create_job_body_sets_required_annotations(job_id, mocked_processor, mimetype, process_id):
    with time_machine.travel(datetime.datetime(2025, 1, 19, 15, 42, 1)):
        job = create_job_body(mocked_processor, job_id, {}, False)

        assert type(job.metadata) is V1ObjectMeta
        assert type(job.metadata.annotations) is dict
        assert len(job.metadata.annotations) == 5
        assert job.metadata.annotations["pygeoapi.io/mimetype"] == mimetype
        assert job.metadata.annotations["pygeoapi.io/identifier"] == job_id
        assert job.metadata.annotations["pygeoapi.io/process_id"] == process_id
        assert job.metadata.annotations["pygeoapi.io/started"] == "2025-01-19T15:42:01.000000Z"
        assert job.metadata.annotations["pygeoapi.io/started"] == job.metadata.annotations["pygeoapi.io/updated"]


class KubernetesProcessorForTesting(KubernetesProcessor):
    def create_job_pod_spec(self, data, job_name):
        return KubernetesProcessor.JobPodSpec(V1PodSpec(containers=[V1Container(name="test-container")]), {})


def test_create_job_body_sets_tolerations(process_id, job_id, toleration):
    p = KubernetesProcessorForTesting(
        {
            "name": process_id,
            "tolerations": [toleration],
        },
        {},
    )
    job = create_job_body(p, job_id, {}, False)

    tolerations = job.spec.template.spec.tolerations
    assert tolerations is not None
    assert len(tolerations) == 1
    assert type(tolerations) is list
    assert len(tolerations) == 1
    assert type(tolerations[0]) is V1Toleration
    assert tolerations[0].key == "toleration-key"
    assert tolerations[0].value == "toleration-value"
    assert tolerations[0].operator == "Equal"
    assert tolerations[0].effect == "NoSchedule"


@pytest.fixture()
def testing_processor() -> KubernetesProcessorForTesting:
    return KubernetesProcessorForTesting({"name": process_id}, {})


def test_create_job_body_sets_finalizer(testing_processor, job_id):
    job = create_job_body(testing_processor, job_id, {}, True)

    assert job.spec.template.metadata.finalizers == [format_log_finalizer()]


def test_create_job_body_set_defaults(testing_processor, job_id):
    job = create_job_body(testing_processor, job_id, {}, False)

    assert job.api_version == "batch/v1"
    assert job.kind == "Job"
    assert job.metadata.name == format_job_name(job_id)
    assert job.spec.backoff_limit == 0
    assert job.spec.ttl_seconds_after_finished == 60 * 60 * 24 * 100

    assert len(job.spec.template.spec.containers[0].env) == 1
    assert job.spec.template.spec.containers[0].env[0].name == "PYGEOAPI_JOB_ID"
    assert job.spec.template.spec.containers[0].env[0].value == job_id


def test_check_auth(testing_processor, process_id):
    assert testing_processor.check_auth()

    testing_processor.is_check_auth = False
    assert not testing_processor.check_auth()

    testing_processor.is_check_auth = None
    assert testing_processor.check_auth()

    testing_processor = KubernetesProcessor({"name": process_id, "check_auth": True}, {})
    assert testing_processor.check_auth()

    testing_processor = KubernetesProcessor({"name": process_id, "check_auth": False}, {})
    assert not testing_processor.check_auth()


def test_add_job_id_env():
    pod_spec = V1PodSpec(
        containers=[V1Container(name="container-0"), V1Container(name="container-1")],
        init_containers=[V1Container(name="init-container-0"), V1Container(name="init.container-1")],
    )

    test_job_id = "test-job-id"
    adjusted_pod_spec = add_job_id_env(pod_spec, test_job_id)

    assert adjusted_pod_spec.containers[0].env[0].name == "PYGEOAPI_JOB_ID"
    assert adjusted_pod_spec.containers[0].env[0].value == test_job_id
    assert adjusted_pod_spec.containers[1].env[0].name == "PYGEOAPI_JOB_ID"
    assert adjusted_pod_spec.containers[1].env[0].value == test_job_id

    assert adjusted_pod_spec.init_containers[0].env[0].name == "PYGEOAPI_JOB_ID"
    assert adjusted_pod_spec.init_containers[0].env[0].value == test_job_id
    assert adjusted_pod_spec.init_containers[1].env[0].name == "PYGEOAPI_JOB_ID"
    assert adjusted_pod_spec.init_containers[1].env[0].value == test_job_id


def test_non_kubernetes_processors_are_rejected(manager):
    with pytest.raises(ValueError) as error:
        manager._execute_handler_async(BaseProcessor({"name": "test"}, {}), {}, "", {})
    assert error.type is ValueError
    assert error.match(
        "'<class 'pygeoapi.process.base.BaseProcessor'>' is not a KubernetesProcessor as required by KubernetesManager."
    )


@pytest.fixture()
def processor() -> KubernetesProcessor:
    return KubernetesProcessor({"name": "test-k8s-processor"}, {})


def test_executions_with_wrong_or_without_token_are_rejected(manager, processor):
    os.environ["PYGEOAPI_K8S_MANAGER_API_TOKEN"] = "right-token"
    with pytest.raises(ProcessorExecuteError) as error:
        manager._execute_handler_async(processor, "", {"token": "wrong-token"})
    assert error.match("ACCESS DENIED: wrong token supplied!")

    with pytest.raises(ProcessorExecuteError) as error:
        manager._execute_handler_async(processor, "", {})
    assert error.match("ACCESS DENIED: no token supplied!")
    del os.environ["PYGEOAPI_K8S_MANAGER_API_TOKEN"]


def test_not_implemented_errors(processor):
    with pytest.raises(NotImplementedError) as error:
        processor.create_job_pod_spec({}, "")
    assert error.match("MUST be implemented by subclass.")

    with pytest.raises(NotImplementedError) as error:
        processor.execute()
    assert error.match("Kubernetes Processes can't be executed directly, use KubernetesManager")
