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
import time_machine
import re
import os
import pytest
from unittest.mock import (
    mock_open,
    patch,
)

from pygeoapi_kubernetes_manager.util import (
    current_namespace,
    format_annotation_key,
    parse_annotation_key,
    format_job_name,
    is_k8s_job_name,
    job_id_from_job_name,
    job_status_from_k8s,
    hide_secret_values,
    now_str,
)

from pygeoapi.util import JobStatus

from kubernetes.client.models.v1_job_status import V1JobStatus


def test_format_annotation_key():
    assert format_annotation_key("test-key") == "pygeoapi.io/test-key"


def test_format_annotation_key_raises_error_on_too_long_key():
    with pytest.raises(ValueError) as error:
        format_annotation_key("too-------------------------------------long-test-annotation-key")
    assert error.type is ValueError
    assert error.match(
        "Specified key 'too-------------------------------------long-test-annotation-key' is longer than allowed API limit 63: '64'"
    )  # noqa: E501


def test_format_annotation_key_with_empty_string():
    assert format_annotation_key("") == "pygeoapi.io/"


def test_parse_annotation_key():
    assert parse_annotation_key("pygeoapi.io/test-key") == "test-key"


def test_parse_annotation_key_parsing_empty_string_return_None():
    assert parse_annotation_key("") is None


def test_parse_annotation_key_parse_None_throws_Error():
    with pytest.raises(TypeError) as error:
        parse_annotation_key(None)
    assert error.type is TypeError
    assert error.match("expected string or bytes-like object, got 'NoneType'")


def test_current_namespace():
    test_namespace = "test-namespace"
    with patch("builtins.open", mock_open(read_data=test_namespace)):
        read_namespace = current_namespace()

    assert test_namespace == read_namespace


def test_current_namespace_use_environment_variable_if_set():
    test_namespace = "test-namespace-env-variable"
    os.environ["PYGEOAPI_K8S_MANAGER_NAMESPACE"] = test_namespace
    read_namespace = current_namespace()
    assert test_namespace == read_namespace
    del os.environ["PYGEOAPI_K8S_MANAGER_NAMESPACE"]


def test_current_namespace_throws_error_when_not_in_cluster_and_required_environment_variable_not_set():
    with pytest.raises(KeyError) as error:
        current_namespace()
    assert error.type is KeyError
    assert error.match(re.escape("Required environment variable 'PYGEOAPI_K8S_MANAGER_NAMESPACE' is missing."))


def test_format_job_name():
    assert format_job_name("test") == "pygeoapi-job-test"


def test_is_k8s_job_name_with_false_name():
    assert is_k8s_job_name("test") is False


def test_is_k8s_job_name_with_correct_name():
    assert is_k8s_job_name("pygeoapi-job-test") is True


def test_job_id_from_job_name_with_correct_name():
    assert job_id_from_job_name("pygeoapi-job-test") == "test"


def test_job_id_from_job_name_with_false_name():
    assert job_id_from_job_name("job-test") == "job-test"


def test_job_status_from_k8s_status_succeeded():
    job_status = V1JobStatus()
    job_status.succeeded = 1
    assert job_status_from_k8s(job_status) == JobStatus.successful


def test_job_status_from_k8s_status_failed():
    job_status = V1JobStatus()
    job_status.succeeded = 0
    job_status.failed = 1
    assert job_status_from_k8s(job_status) == JobStatus.failed


def test_job_status_from_k8s_status_active():
    job_status = V1JobStatus()
    job_status.succeeded = 0
    job_status.failed = 0
    job_status.active = 1
    assert job_status_from_k8s(job_status) == JobStatus.running


def test_job_status_from_k8s_status_other():
    job_status = V1JobStatus()
    job_status.succeeded = None
    job_status.failed = None
    job_status.active = None
    assert job_status_from_k8s(job_status) == JobStatus.accepted


def test_hide_secret_values():
    assert hide_secret_values(
        {
            "secret": "secret",
            "key": "key",
            "password": "password",
            "another-kee": "another-value",
            "token": "token",
        }
    ) == {"secret": "*", "key": "*", "password": "*", "another-kee": "another-value", "token": "*"}


def test_now_str():
    with time_machine.travel(datetime.datetime(2025, 1, 19, 15, 42, 1)):
        assert now_str() == "2025-01-19T15:42:01.000000Z"
