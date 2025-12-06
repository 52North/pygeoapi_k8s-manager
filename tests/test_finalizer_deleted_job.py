
import datetime
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client import V1PodList

from pygeoapi_k8s_manager.finalizer import KubernetesFinalizerController

@pytest.fixture()
def finalizer():
    return KubernetesFinalizerController("")

def test_handle_job_ended_event_handles_deleted_job(finalizer):
    finalizer.is_upload_logs_to_s3 = False
    k8s_core_api = MagicMock()
    k8s_core_api.list_namespaced_pod.return_value = V1PodList(items=[])
    
    test_job = MagicMock()
    test_job.metadata.name = "test-job"
    test_job.metadata.deletion_timestamp = datetime.datetime.now()

    with (
        patch(
            "pygeoapi_k8s_manager.finalizer.KubernetesFinalizerController.upload_logs_to_s3"
        ) as mocked_upload_logs_to_s3,
        patch("pygeoapi_k8s_manager.util.get_logs_for_pod") as mocked_get_logs_for_pod,
    ):
        finalizer.handle_job_ended_event(
            k8s_core_api=k8s_core_api,
            job=test_job,
        )

    mocked_get_logs_for_pod.assert_not_called()
    mocked_upload_logs_to_s3.assert_not_called()
