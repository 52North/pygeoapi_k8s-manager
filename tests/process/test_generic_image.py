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
import pytest

from pygeoapi_kubernetes_manager.process import GenericImageProcessor


@pytest.fixture()
def processor() -> GenericImageProcessor:
    return GenericImageProcessor(
        processor_def={
            "name": "test",
            "metadata": {
                "version": "0.1",
                "id": "ingestor-cds-process",
                "title": {
                    "en": "CDS process",
                    "de": "CDS Prozess",
                },
                "keywords": [
                    "test-keyword-1",
                    "test-keyword-2",
                ],
                "description": {
                    "en": "english-test-description",
                    "de": "german-test-description",
                },
                "links": [
                    {
                        "type": "text/html",
                        "rel": "about",
                        "title": "repository",
                        "href": "https://github.com/52North/pygeoapi_k8s-manager/tree/main/pygeoapi_kubernetes_manager/process/generic_image.py",  # noqa: E501
                        "hreflang": "en-UK",
                    }
                ],
                "inputs": {
                    "name": {
                        "title": "Name",
                        "description": "The name of the person or entity that you wish to be echoed back as an output",
                        "schema": {"type": "string"},
                        "minOccurs": 1,
                        "maxOccurs": 1,
                        "keywords": ["full name", "personal"],
                    }
                },
                "outputs": {
                    "test-output": {
                        "title": "test-output-title",
                        "description": "test-output-description",
                        "schema": {
                            "type": "object",
                            "contentMediaType": "test-output/mimetype",
                        },
                    }
                },
                "example": {
                    "inputs": {
                        "name": "test-name"
                    }
                }
            },
            "default_image": "example-image",
            "command": ["test-command"],
            "mimetype": "application/json",
            "image_pull_secret": "test-image-pull-secret",
            "resources": {
                "requests": {
                    "memory": "test-memory-request",
                    "cpu": "test-cpu-request",
                },
                "limits": {
                    "memory": "test-memory-limit",
                    "cpu": "test-cpu-limit",
                },
            },
            "storage": [
                {
                    "name": "test-storage-name",
                    "mount_path": "test-storage-mount-path",
                    "persistent_volume_claim_name": "test-storage-pvc-name",
                },
            ],
            "env": [
                # env from secrets
                {
                    "name": "env_from_secret_name",
                    "secret_name": "env_from_secret_secret_name",
                    "secret_key": "env_from_secret_secret_key",
                },
                # simple env
                {
                    "name": "simple_env_name",
                    "value": "simple_env_value",
                },
                {
                    "name": "simple_env_boolean",
                    "value": False,
                }
            ],
        }
    )


def test_processor_def_is_parsed(processor):
    assert len(processor.command) == 1
    assert processor.command[0] == "test-command"
    assert processor.supports_outputs is True
    assert processor.default_image == "example-image"
    assert processor.mimetype == "test-output/mimetype"
    assert processor.image_pull_secret == "test-image-pull-secret"

    meta = processor.metadata
    assert meta["id"] == "ingestor-cds-process"
    assert meta["version"] == "0.1"
    assert meta["title"] == {
        "en": "CDS process",
        "de": "CDS Prozess",
    }
    assert len(meta["links"]) == 1
    assert meta["links"][0] == {
        "type": "text/html",
        "rel": "about",
        "title": "repository",
        "href": "https://github.com/52North/pygeoapi_k8s-manager/tree/main/pygeoapi_kubernetes_manager/process/generic_image.py",  # noqa: E501
        "hreflang": "en-UK",
    }
    assert len(meta["inputs"]) == 1
    assert meta["inputs"]["name"] == {
        "title": "Name",
        "description": "The name of the person or entity that you wish to be echoed back as an output",
        "schema": {"type": "string"},
        "minOccurs": 1,
        "maxOccurs": 1,
        "keywords": ["full name", "personal"],
    }
    assert len(meta["outputs"]) == 1
    assert meta["outputs"]["test-output"] == {
        "title": "test-output-title",
        "description": "test-output-description",
        "schema": {"type": "object", "contentMediaType": "test-output/mimetype"},
    }
    assert len(meta["keywords"]) == 2
    assert meta["keywords"][0] == "test-keyword-1"
    assert meta["keywords"][1] == "test-keyword-2"
    assert len(meta["example"]["inputs"]) == 1
    assert meta["example"]["inputs"]["name"] == "test-name"

    env = processor.env
    assert len(env) == 3
    assert env[0]["name"] == "env_from_secret_name"
    assert env[0]["secret_name"] == "env_from_secret_secret_name"
    assert env[0]["secret_key"] == "env_from_secret_secret_key"
    assert env[1]["name"] == "simple_env_name"
    assert env[1]["value"] == "simple_env_value"
    assert env[2]["name"] == "simple_env_boolean"
    assert env[2]["value"] is False

    res = processor.resources
    assert len(res) == 2
    assert res["requests"]["cpu"] == "test-cpu-request"
    assert res["requests"]["memory"] == "test-memory-request"
    assert res["limits"]["cpu"] == "test-cpu-limit"
    assert res["limits"]["memory"] == "test-memory-limit"

    storage = processor.storage
    assert len(storage) == 1
    assert storage[0]["name"] == "test-storage-name"
    assert storage[0]["mount_path"] == "test-storage-mount-path"
    assert storage[0]["persistent_volume_claim_name"] == "test-storage-pvc-name"


def test_outputs_mimetype_detection(processor):
    assert processor.mimetype == "test-output/mimetype"
    assert processor._output_mimetype({}) is None
    assert processor._output_mimetype({
        "outputs": {
            "output-one": {},
            "output-two": {}
        }
    }) == "application/json"


@pytest.fixture()
def data() -> dict:
    return {
        "input-str-id": "input-str-value",
        "input-int-id": 42,
        "input-boolean-id": False,
    }


def test_create_job_pod_spec(processor, data):
    spec = processor.create_job_pod_spec(data=data, job_name="test_job")

    assert spec
    assert spec.extra_annotations

    annotations = spec.extra_annotations
    assert annotations["job-name"] == "test_job"
    assert annotations["parameters"] == \
        "{\"input-str-id\": \"input-str-value\", \"input-int-id\": 42, \"input-boolean-id\": false}"

    assert spec.pod_spec

    pod = spec.pod_spec
    assert pod.tolerations is None
    assert pod.image_pull_secrets[0].name == "test-image-pull-secret"
    assert len(pod.volumes) == 1
    assert pod.volumes[0].name == "test-storage-name"
    assert pod.volumes[0].persistent_volume_claim.claim_name == "test-storage-pvc-name"
    assert len(pod.containers) == 1

    container = pod.containers[0]
    assert container.image == "example-image"
    assert len(container.command) == 1
    assert container.command[0] == "test-command"
    assert container.name == "generic-image-processor"
    assert len(container.volume_mounts) == 1
    assert container.volume_mounts[0].mount_path == "test-storage-mount-path"
    assert container.volume_mounts[0].name == "test-storage-name"

    env = container.env
    assert len(env) == 4
    assert env[0].name == "env_from_secret_name"
    assert env[0].value_from.secret_key_ref.name == "env_from_secret_secret_name"
    assert env[0].value_from.secret_key_ref.key == "env_from_secret_secret_key"
    assert env[1].name == "simple_env_name"
    assert env[1].value == "simple_env_value"
    assert env[2].name == "simple_env_boolean"
    assert env[2].value == "False"
    assert env[2].value is not False

    res = container.resources
    assert res
    assert len(res.limits) == 2
    assert len(res.requests) == 2
    assert res.limits["cpu"] == "test-cpu-limit"
    assert res.limits["memory"] == "test-memory-limit"
    assert res.requests["cpu"] == "test-cpu-request"
    assert res.requests["memory"] == "test-memory-request"


def test_absence_of_image_pull_secret(processor, data):
    processor.image_pull_secret = None
    job_pod_spec = processor.create_job_pod_spec(data=data, job_name="test_job")

    assert job_pod_spec.pod_spec.image_pull_secrets is None


def test_absence_of_storage(processor, data):
    processor.storage = None
    job_pod_spec = processor.create_job_pod_spec(data=data, job_name="test-job")

    assert job_pod_spec.pod_spec.volumes is None
    assert job_pod_spec.pod_spec.containers[0].volume_mounts is None


def test_absence_of_resources(processor, data):
    processor.resources = None
    with pytest.raises(NotImplementedError) as error:
        processor.create_job_pod_spec(data=data, job_name="test-job")

    assert error.type == NotImplementedError
    assert error.match("Default resources not implemented. Please specify in process resource!")


def test_absence_of_env(processor, data):
    processor.env = {}
    job_pod_spec = processor.create_job_pod_spec(data=None, job_name="test-job")

    assert job_pod_spec.pod_spec.containers[0].env is None


def test_inputs_are_provided_as_env(processor, data):
    job_pod_spec = processor.create_job_pod_spec(data=data, job_name="test-job")

    assert job_pod_spec.pod_spec.containers[0].env[3].name == "PYGEOAPI_K8S_MANAGER_INPUTS"
    assert job_pod_spec.pod_spec.containers[0].env[3].value == \
        "{\"input-str-id\": \"input-str-value\", \"input-int-id\": 42, \"input-boolean-id\": false}"
