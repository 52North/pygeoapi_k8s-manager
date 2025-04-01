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
import logging

import copy
from typing import Any

from pygeoapi_kubernetes_manager.manager import KubernetesProcessor

from pygeoapi_kubernetes_manager.util import ProcessorClientError

from kubernetes import client as k8s_client
from kubernetes.client.models import (
    V1EnvVar,
    V1EnvVarSource,
    V1ResourceRequirements,
    V1SecretKeySelector,
)


LOGGER = logging.getLogger(__name__)

#: Process metadata and description
PROCESS_METADATA = {
    'version': 'should-be-overridden-by-config',
    'id': 'should-be-overridden-by-config',
    'title': {
        'en': 'should-be-overridden-by-config',
    },
    'description': {
        'en': 'should-be-overridden-by-config.',
    },
    'jobControlOptions': ['async-execute'],
    'keywords': ['should-be-overridden-by-config', 'k8s', 'KubernetesManager'],
    'links': [],
    'inputs': {
        # TODO should be filed programmatically
    },
    'outputs': {},
    'example': {}
}


class GenericImageProcessor(KubernetesProcessor):
    """Generic Image Processor"""


    def __init__(self, processor_def: dict):
        metadata = copy.deepcopy(PROCESS_METADATA)
        if "metadata" in processor_def:
            metadata.update(processor_def["metadata"])
        super().__init__(processor_def, metadata)

        self.default_image: str = processor_def["default_image"]
        self.command: str = processor_def["command"]
        self.image_pull_secret: str = processor_def["image_pull_secret"] if "image_pull_secret" in processor_def.keys() else None
        self.resources: dict = processor_def["resources"]
        self.env: dict = processor_def["env"] if "env" in processor_def.keys() else {}
        self.mimetype: str = self._output_mimetype(processor_def["metadata"])
        self.supports_outputs: bool = True if self.mimetype else False

    def _output_mimetype(self, metadata: dict) -> str:
        """
        if no outputs -> None
        if one output -> contentMediaType
        if more than one output -> application/json"

        :returns mimetype: None if no outputs, outputs::schema::contentMediaType if one output, else application/json
        """
        if "outputs" not in metadata.keys() or len(metadata["outputs"]) == 0:
            return None
        elif len(metadata["outputs"]) == 1:
            return next(iter(metadata["outputs"].values()))["schema"]["contentMediaType"]
        else:
            return "application/json"

    def _env_from_processor_spec(self) -> list[V1EnvVar]:
        """
        name: env-name
        secret_name: secret-name
        secret_key: secret-key
        || || ||
        \/ \/ \/
        name: env-name
          valueFrom:
            secretKeyRef:
              name: secret-name
              key: secret-key

        or

        name: env-name
        value: env-value
        || || ||
        \/ \/ \/
        name: env-name
        value: env-value

        :returns list[V1EnvVar]
        """
        if not self.env:
            return None
        k8s_env = []
        for env_variable in self.env:
            if "secret_name" in env_variable.keys():
                k8s_env.append(V1EnvVar(
                    name=env_variable["name"],
                    value_from=V1EnvVarSource(
                        secret_key_ref=V1SecretKeySelector(
                            key=env_variable["secret_key"],
                            name=env_variable["secret_name"],
                        ))))
            else:
                k8s_env.append(V1EnvVar(
                    name=env_variable["name"],
                    value=str(env_variable["value"]),
                ))
        return k8s_env

    def _res_from_processor_spec(self) -> V1ResourceRequirements:
        return V1ResourceRequirements(
            limits=self.resources["limits"],
            requests=self.resources["requests"])

    def create_job_pod_spec(self,
        data: dict,
        job_name: str
    ) -> KubernetesProcessor.JobPodSpec:
        LOGGER.debug("Starting job with data %s", data)

        extra_podspec = self._add_tolerations()

        if self.image_pull_secret:
            extra_podspec["image_pull_secrets"] = [
                k8s_client.V1LocalObjectReference(name=self.image_pull_secret)
            ]

        k8s_env = self._env_from_processor_spec()
        k8s_res = self._res_from_processor_spec()

        image_container = k8s_client.V1Container(
            name="generic-image-processor",
            image=self.default_image,
            command=self.command,
            env=k8s_env,
            resources=k8s_res
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
                "parameters" : json.dumps(data),
                "job-name": job_name,
            },
        )

    def __repr__(self):
        return f'<GenericImageProcessor> {self.name}'
