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
                "description": {
                    "en": "english-test-description",
                    "de": "german-test-description",
                },
                "links": [
                    {
                        "type": "text/html",
                        "rel": "about",
                        "title": "repository",
                        "href": "https://github.com/52North/pygeoapi_k8s-manager/tree/main/pygeoapi_kubernetes_manager/process/generic_image.py",
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
            },
            "default_image": "example-image",
            "command": "test-command",
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
            ],
        }
    )


def test_processor_def_is_parsed(processor):
    assert processor.command == "test-command"
    assert processor.supports_outputs == True
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
        "href": "https://github.com/52North/pygeoapi_k8s-manager/tree/main/pygeoapi_kubernetes_manager/process/generic_image.py",
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

    env = processor.env
    assert len(env) == 2
    assert env[0]["name"] == "env_from_secret_name"
    assert env[0]["secret_name"] == "env_from_secret_secret_name"
    assert env[0]["secret_key"] == "env_from_secret_secret_key"
    assert env[1]["name"] == "simple_env_name"
    assert env[1]["value"] == "simple_env_value"

    res = processor.resources
    assert len(res) == 2
    assert res["requests"]["cpu"] == "test-cpu-request"
    assert res["requests"]["memory"] == "test-memory-request"
    assert res["limits"]["cpu"] == "test-cpu-limit"
    assert res["limits"]["memory"] == "test-memory-limit"


def test_outputs_mimetype_detection(processor):
    assert processor.mimetype == "test-output/mimetype"
    assert processor._output_mimetype({}) == None
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
    assert annotations["parameters"] == json.dumps(data)

    assert spec.pod_spec

    pod = spec.pod_spec
    assert pod.tolerations is None
    assert pod.image_pull_secrets[0].name == "test-image-pull-secret"
    assert len(pod.containers) == 1

    container = pod.containers[0]
    assert container.image == "example-image"
    assert container.command == "test-command"

    env = container.env
    assert len(env) == 2
    assert env[0].name == "env_from_secret_name"
    assert env[0].value_from.secret_key_ref.name == "env_from_secret_secret_name"
    assert env[0].value_from.secret_key_ref.key == "env_from_secret_secret_key"
    assert env[1].name == "simple_env_name"
    assert env[1].value == "simple_env_value"

    res = container.resources
    assert res
    assert len(res.limits) == 2
    assert len(res.requests) == 2
    assert res.limits["cpu"] == "test-cpu-limit"
    assert res.limits["memory"] == "test-memory-limit"
    assert res.requests["cpu"] == "test-cpu-request"
    assert res.requests["memory"] == "test-memory-request"
