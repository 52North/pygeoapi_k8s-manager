# =================================================================
#
# Authors: Tom Kralidis <tomkralidis@gmail.com>
#          Francesco Martinelli <francesco.martinelli@ingv.it>
#          Eike Hinderk Jürrens <e.h.juerrens@52north.org>
#
# Copyright (c) 2022 Tom Kralidis
# Copyright (c) 2024 Francesco Martinelli
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
from dataclasses import dataclass
import json
import logging

import copy
from typing import Any

from pygeoapi_kubernetes_manager.manager import KubernetesProcessor

from pygeoapi_kubernetes_manager.util import ProcessorClientError

from kubernetes import client as k8s_client


LOGGER = logging.getLogger(__name__)

#: Process metadata and description
PROCESS_METADATA = {
    'version': '0.1.0',
    'id': 'hello-world-k8s',
    'title': {
        'en': 'Hello World k8s',
    },
    'description': {
        'en': 'An example process that takes a name as input, and echoes '
              'it back as output. Intended to demonstrate a simple '
              'process with a single literal input.',
    },
    'jobControlOptions': ['async-execute'],
    'keywords': ['hello world', 'example', 'echo', 'k8s', 'KubernetesManager'],
    'links': [{
        'type': 'text/html',
        'rel': 'about',
        'title': 'information',
        'href': 'https://example.org/process',
        'hreflang': 'en-US'
    }],
    'inputs': {
        'name': {
            'title': 'Name',
            'description': 'The name of the person or entity that you wish to'
                           'be echoed back as an output',
            'schema': {
                'type': 'string'
            },
            'minOccurs': 1,
            'maxOccurs': 1,
            'keywords': ['full name', 'personal']
        },
        'message': {
            'title': 'Message',
            'description': 'An optional message to echo as well',
            'schema': {
                'type': 'string'
            },
            'minOccurs': 0,
            'maxOccurs': 1,
            'keywords': ['message']
        }
    },
    'outputs': {
        'echo': {
            'title': 'Hello, world',
            'description': 'A "hello world" echo with the name and (optional)'
                           ' message submitted for processing',
            'schema': {
                'type': 'object',
                'contentMediaType': 'application/json'
            }
        }
    },
    'example': {
        'inputs': {
            'name': 'World',
            'message': 'An optional message.',
        }
    }
}


class HelloWorldK8sProcessor(KubernetesProcessor):
    """Hello World K8s Processor example

    Test via

        curl -X 'POST' \
            'http://localhost/processes/hello-world-k8s/execution' \
            -H 'accept: application/json' \
            -H 'Content-Type: application/json' \
            -d '{
                "inputs": {
                    "message": "Am I in TV, now?",
                    "name": "John Doe"
                }
            }'

    """


    @dataclass(frozen=True)
    class Parameters():
        message: str
        name: str


    def __init__(self, processor_def: dict):
        super().__init__(processor_def, PROCESS_METADATA)

        self.supports_outputs = True
        self.default_image: str = processor_def["default_image"]
        self.command: str = processor_def["command"]
        self.image_pull_secret: str = processor_def["image_pull_secret"]
        self.tolerations: list = processor_def["tolerations"] if "tolerations" in processor_def else None


    def create_job_pod_spec(self,
        data: dict,
        job_name: str
    ) -> KubernetesProcessor.JobPodSpec:
        LOGGER.debug("Starting job with data %s", data)

        try:
            requested = self.Parameters(**data)
        except (TypeError, KeyError) as e:
            raise ProcessorClientError(user_msg=f"Invalid parameter: {e}") from e

        extra_podspec = {}
        if self.image_pull_secret:
            extra_podspec["image_pull_secrets"] = [
                k8s_client.V1LocalObjectReference(name=self.image_pull_secret)
            ]

        image_container = k8s_client.V1Container(
            name="hello-world-k8s",
            image=self.default_image,
            command=[
                "/bin/sh",
                "-c",
                f"{self.command}; echo \"Hello '{requested.name}': '{requested.message}'.\"",
            ],
        )

        return KubernetesProcessor.JobPodSpec(
            pod_spec=k8s_client.V1PodSpec(
                restart_policy="Never",
                # NOTE: first container is used for status check
                containers=[image_container], # + extra_config.containers,
                # we need this to be able to terminate the sidecar container
                # https://github.com/kubernetes/kubernetes/issues/25908
                share_process_namespace=True,
                **extra_podspec,
                enable_service_links=False,
            ),
            extra_annotations={
                "parameters" : json.dumps({
                    "name": requested.name,
                    "message": requested.message,
                }),
                "job-name": job_name,
            },
        )


    def __repr__(self):
        return f'<HelloWorldProcessor> {self.name}'
