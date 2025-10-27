# pygeoapi - kubernetes manager

Extends [pygeoapi](https://pygeoapi.io/) by a manager for kubernetes jobs and a process to execute any container image on a cluster.

## Usage

### GenericImageProcessor

The required and supported configuration options are outlined in the example configuration `pygeoapi-config.yaml`.

The given inputs are injected into the k8s job pod via the environment variable `PYGEOAPI_K8S_MANAGER_INPUTS`.
Hence, your process wrapper MUST use this variable for dynamic inputs.
Static inputs can be injected using your environment variable definitions.

Each execution of a GenericImageProcessor requires an auth token to be provided as input `token`.
It MUST match the value of the environment variable `PYGEOAPI_K8S_MANAGER_API_TOKEN`.
An `ProcessorExecuteError` will be raised if not given and matching.
The check for this token can be disabled by using the processor definition and setting the property `check_auth` to `False`.
In addition, your processor can override the method `check_auth`.

## k8s Configuration Requirements

Required RBAC rules:

```shell
  Resources    Non-Resource URLs  Resource Names  Verbs
---------    -----------------  --------------  -----
jobs.batch   []                 []              [get list watch create update patch delete]
events       []                 []              [get watch list]
pods/log     []                 []              [get watch list]
pods/status  []                 []              [get watch list]
pods         []                 []              [get watch list patch]
```

See [k8s manifest examples](./k8s-manifests/) for an example set-up, that outlines the required adjustments to your cluster.
The set-up requires a secret `k8s-job-manager` with key `token` in the same namespace of the deployment (*here*: `default`), that could be created with the following command:

```shell
kubectl create secret generic -n default k8s-job-manager --from-literal=token=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 32; echo)
```

## Job Logs Finalizer

The manager comes with an built-in [k8s finalizer](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) controller to handle the logs of the jobs and persist them in an s3 bucket.
The according configuration requires the following environment variables and activation in the pygeoapi configuration.
It is implemented in the `finalizer.py` module in the class `KubernetesFinalizerController`.
In addition, this finalizer is used to persist the result mimetype and value.
The logs are parsed during finalizing.
The result mimetype is parsed from log statements with the marker: `PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE`.
The according log line must contain this and split the mimetype with `:`, e.g. `[2025-06-23T13:00:18Z | pygeoapi_k8s_manager.process.generic_image::result_logging.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE: application/json`.
The result value MUST be provided after a log statement with the marker `PYGEOAPI_K8S_MANAGER_RESULT_START`, e.g. parsing the following snippet results in the given result:

- *Log Snippet*

  ```plain
  [2025-06-23T13:05:00Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] DEBUG - Event 'ADDED' with object job 'howis-ingest-29178065' received
  [2025-06-23T13:05:00Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'howis-ingest-29178065' received
  [2025-06-23T13:05:11Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'howis-ingest-29178065' received
  [2025-06-23T13:05:17Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'howis-ingest-29178065' received
  [2025-06-23T13:05:17Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE:application/json
  [2025-06-23T13:05:17Z | pygeoapi_kubernetes_manager.finalizer::finalizer.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_START
  {
      "id": "pygeoapi-test-process-id",
      "value": "result-value"
  }
  ```

- *Parsed Result Value*

  ```json
  {
      "id": "pygeoapi-test-process-id",
      "value": "result-value"
  }
  ```

**pygeoapi configuration snippet**:

```yaml
server:
  manager:
    name: pygeoapi_k8s_manager.manager.KubernetesManager
    finalizer_controller: true
```

**environment variables available**:

| **name** | **comment** |
|---|---|
| `PYGEOAPI_JOB_ID` | Each container (normal and init) of the job pod will receive this variable containing the pygeoapi provided id of the current job, e.g. `99755242-31af-11f0-80bd-0255ac10006c`. |

**environment variables to configure**:

| **name** | **comment** |
|---|---|
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT` | Endpoint of the bucket hosting service, similar to `FSSPEC_S3_ENDPOINT_URL`, e.g. OTC: `https://obs.eu-de.otc.t-systems.com` |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY` | The access key with permission to upload files to the given "path", similar to `FSSPEC_S3_KEY` |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET` | The access key secret for the key, similar to `FSSPEC_S3_SECRET`. |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME` | Name of the bucket. |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX` | The "folder" the log files will be uploaded to. It MUST end with an `/`. |

Ensure, that the bucket is **not publicly** available in the internet, because the logs might leak confidential information and should be consulted only by technical personnel.

*Hint*: The controller will cancel the log file upload, if any of these variables is not configured and log errors.
This will result in k8s resources **not being deleted, which requires manual interaction**!

## Development

We are using [uv](https://docs.astral.sh/uv/) to manage the project.

You can use a kind based k8s cluster for testing.
[Install kind following the according instructions](https://kind.sigs.k8s.io/docs/user/quick-start/#installation).
The project specific kind set-up is outlined in [/k8s-kind/](./k8s-kind/README.md).

### Dependency Management with uv

- Add normal dependency: `uv add dependency`
- Add `dev` dependency: `uv add --dev dependency`
- Add `docker` dependency: `uv add --group docker dependency`

The docker dependency group is used during building the docker image, which is based on pygeoapi, hence no pygeoapi package needs to be installed.

### Debugging with vscode

The project come with vscode debug launch configuration, that works with the kind cluster configuration.
The details can be found in the two folders in `.vscode/` and `k8s-kind/`.
For debugging, only the minio set-up is required.

## Container

**Build** the latest container image with docker using the following command:

```shell
VERSION=0.17 \
REGISTRY=docker.io \
IMAGE=52north/pygeoapi-k8s-manager \
; \
docker build \
  -t "${REGISTRY}/${IMAGE}:latest" \
  -t "${REGISTRY}/${IMAGE}:${VERSION}" \
  --build-arg VERSION="$VERSION" \
  --build-arg BUILD_DATE=$(date -u --iso-8601=seconds) \
  --build-arg GIT_COMMIT=$(git rev-parse --short=20 -q --verify HEAD) \
  --build-arg GIT_TAG=$(git describe --tags) \
  --build-arg GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD) \
  .
```

**Run** the image locally for testing:

*Hint*:
Notice the **whitespace before the command** to prevent the secrets to be stored in the history of the shell.
If the used shell does NOT support this, ensure another procedure to prevent leaking of the credentials

```shell
 REGISTRY=docker.io \
IMAGE=52north/pygeoapi-k8s-manager \
docker run \
  --env PYGEOAPI_K8S_MANAGER_NAMESPACE=default \
  --env PYGEOAPI_K8S_MANAGER_API_TOKEN=token \
  --env PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT=https://obs.eu-de.otc.t-systems.com \
  --env PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY=my-key \
  --env PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET=my-secret \
  --env PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME=my-bucket \
  --env PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX=my-k8s-job-manager/logs/ \
  --rm \
  --name k8s-manager \
  -p 80:80 \
  --volume=./pygeoapi-config.yaml:/pygeoapi/local.config.yml \
  --volume="$HOME/.kube/:/root/.kube/" \
  "${REGISTRY}/${IMAGE}:latest"
```

**Scan** the image for vulnerabilities

```shell
docker run -ti --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /tmp/aquasec-trivy-cache:/root/.cache/ \
    aquasec/trivy:latest \
    image \
        --scanners vuln \
        --format table \
        --severity CRITICAL,HIGH \
        --ignore-unfixed \
        52north/pygeoapi-k8s-manager:latest
```

**Upload to registry** after [successful login](https://docs.otc.t-systems.com/software-repository-container/umn/image_management/uploading_an_image_through_the_client.html#procedure):

```shell
docker push --all-tags 52north/pygeoapi-k8s-manager
```

or

```shell
docker push 52north/pygeoapi-k8s-manager:latest && \
docker push "52north/pygeoapi-k8s-manager:$VERSION"
```

## Tests

Execute the following CURL command for testing:

```shell
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
```

Install test requirements in local env via:

```shell
uv pip install --group dev
```

## License

This work is licensed in [Apache 2.0](./LICENSE).

Create/Update the NOTICE file using the following command **AFTER** building the image:

```shell
docker run \
  --rm \
  --entrypoint "/bin/bash" \
  52north/pygeoapi-k8s-manager:latest \
  -c "pip install --no-warn-script-location --no-cache-dir pip-licenses > /dev/null && /usr/local/bin/pip-licenses -f plain | grep -v pygeoapi-k8s-manager"
```

The developments are based on [pygeoapi-kubernetes-papermill](https://github.com/eoxhub-workspaces/pygeoapi-kubernetes-papermill).

## Funding

The development of the "pygeoapi - kubernetes manager" implementation was supported by several organizations and projects.
Among other we would like to thank the following organizations and projects

|             Project/Logo             | Description                                                                                                                                                                                                                                                                                                                                |
|:------------------------------------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ![DIRECTED](./img/logo_directed.png) | [DIRECTED](https://52north.org/solutions/directed/) aims to reduce vulnerability to extreme weather events and foster disaster-resilient European societies by promoting interoperability of data, models, communication and governance on all levels and between all actors of the disaster risk management and climate adaptation process. |
|   ![I-CISK](./img/logo_i-cisk.png)   | [I-CISK](https://52north.org/solutions/i-cisk/) will empower local communities to build and use tailored local Climate Services to adapt to climate change.                                                                                                                                                                                |
| ![TwinShip](./img/twinship_logo.png) | [TwinShip](https://twin-ship.eu/) aims to reduce Greenhouse Gas emissions in international shipping. It is co-funded by the European Union’s Horizon Europe programme under grant agreement No. 101192583.                                                                                                                                 |
|  ![WEB-AIS](./img/logo_web-ais.png)  | [WEB-AIS](https://52north.org/solutions/web-based-agricultural-information-system-webais-for-bangladesh/) aims for improving water management in Bangladesh in times of climate change impacts.                                                                                                                                                                                                            |
