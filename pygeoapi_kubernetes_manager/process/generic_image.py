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
        self.image_pull_secret: str = processor_def["image_pull_secret"]
        self.env: dict = processor_def["env"]
        self.resources: dict = processor_def["resources"]
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

    def __repr__(self):
        return f'<GenericImageProcessor> {self.name}'
