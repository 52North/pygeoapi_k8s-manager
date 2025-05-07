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
import re
from pygeoapi_kubernetes_manager.process import HelloWorldK8sProcessor
import pytest

from pygeoapi_kubernetes_manager.util import ProcessorClientError


@pytest.fixture()
def processor() -> HelloWorldK8sProcessor:
    return HelloWorldK8sProcessor(processor_def={
        "name": "pygeoapi_kubernetes_manager.process.HelloWorldK8sProcessor",
        "default_image": "test-image",
        "command": "test-command",
        "image_pull_secret": "test-image-pull-secret"
    }
    )


def test_init(processor):
    assert processor.command == "test-command"
    assert processor.default_image == "test-image"
    assert processor.name == "pygeoapi_kubernetes_manager.process.HelloWorldK8sProcessor"
    assert processor.tolerations is None


@pytest.fixture()
def data() -> dict:
    return {
        "message": "test-message",
        "name": "test-name",
    }


def test_create_job_pod_spec(processor, data):
    job_pod_spec = processor.create_job_pod_spec(data=data, job_name="test-job-name")

    assert job_pod_spec is not None
    assert job_pod_spec.extra_annotations == {
        'parameters': '{"name": "test-name", "message": "test-message"}',
        'job-name': 'test-job-name',
    }
    pod = job_pod_spec.pod_spec
    assert pod.active_deadline_seconds is None
    assert pod.affinity is None
    assert pod.automount_service_account_token is None
    assert len(pod.image_pull_secrets) == 1
    assert pod.image_pull_secrets[0].name == "test-image-pull-secret"
    assert len(pod.containers) == 1
    container = pod.containers[0]
    assert container.image == "test-image"
    assert container.name == "hello-world-k8s"


def test_raise_error_on_wrong_input(processor):
    with pytest.raises(ProcessorClientError) as error:
        processor.create_job_pod_spec(data={}, job_name=None)

    assert error.type is ProcessorClientError
    assert error.match(re.escape("Invalid parameter: HelloWorldK8sProcessor.Parameters.__init__() missing 2 required positional arguments: 'message' and 'name'"))  # noqa: E501
