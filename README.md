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

### Job Naming

The environment variable `PYGEOAPI_K8S_MANAGER_JOB_NAME_PREFIX` (default `pygeoapi-job-`) defines the prefix of every job created by the manager.
This prefix is also the identification criterion for the jobs that belong to the manager: listing, status, results and the log finalizer all match jobs by this prefix.
It is read once at startup, so changing it does **not** take effect on-the-fly — a restart is required.
Treat the prefix as a fixed, deploy-time setting that must stay stable for the lifetime of the jobs:
changing it strands all jobs created with the previous prefix (they disappear from the job list, can no longer be retrieved, and are never picked up by the finalizer, so their pods can remain undeleted).

### Job Pod Security Context

Every job pod the manager creates is hardened with a baseline `securityContext` by default:

- pod-level: `seccompProfile.type: RuntimeDefault`
- container-level (applied to all containers and init containers): `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`

This baseline hardens most workloads without breaking arbitrary images.
The context can be adjusted on two levels; precedence is **`processor_def` > environment variable > baseline default**.

Globally, the context can be set via environment variables as JSON using the Kubernetes API field names (i.e. `camelCase`).
Set a variable to `off` (or `none`) to disable that context.
If a variable contains invalid JSON, no job is started and a `ProcessorExecuteError` is raised — the manager never silently falls back to a weaker context.

| Environment variable                                  | Description                             |
| ----------------------------------------------------- | --------------------------------------- |
| `PYGEOAPI_K8S_MANAGER_JOB_POD_SECURITY_CONTEXT`       | Pod-level `securityContext` as JSON.    |
| `PYGEOAPI_K8S_MANAGER_JOB_CONTAINER_SECURITY_CONTEXT` | Container-level `securityContext` JSON. |

Per process, the context can be set in the processor definition (`pygeoapi-config.yaml`) using the keys `pod_security_context` and `container_security_context`.
Setting a key to `null` disables that context for the process.

The following recommended hardened ("restricted") example may require adjustments for arbitrary images, e.g. a writable root filesystem or a specific UID.

```yaml
    processor:
      name: pygeoapi_k8s_manager.process.GenericImageProcessor
      pod_security_context:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      container_security_context:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
```

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

## Job Finalizer

The manager comes with an built-in [k8s finalizer](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) controller to handle the logs and the result mimetype plus value of the jobs.
The according configuration requires the following environment variables and activation in the pygeoapi configuration.
It is implemented in the `finalizer.py` module in the class `KubernetesFinalizerController`.
The logs are parsed during finalizing.
The result mimetype is parsed from log statements with the marker: `PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE`.
The according log line must contain this and split the mimetype with `:`, e.g. `[2025-06-23T13:00:18Z | pygeoapi_k8s_manager.process.generic_image::result_logging.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE:application/json`.
The result value MUST be provided after a log statement with the marker `PYGEOAPI_K8S_MANAGER_RESULT_START`, e.g. parsing the following snippet results in the given result:

- *Log Snippet*

  ```plain
  ...finalizer.py:97 | 14] DEBUG - Event 'ADDED' with object job 'ingest-29178065' received
  ...finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'ingest-29178065' received
  ...finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'ingest-29178065' received
  ...finalizer.py:97 | 14] DEBUG - Event 'MODIFIED' with object job 'ingest-29178065' received
  ...finalizer.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_MIMETYPE:application/json
  ...finalizer.py:97 | 14] INFO - PYGEOAPI_K8S_MANAGER_RESULT_START
  {
      "id": "pygeoapi-process-id",
      "value": "result-value"
  }
  ```

- *Parsed Result Value*

  ```json
  {
      "id": "pygeoapi-process-id",
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

⚠️*Hint*:
If the finalizer is not used, the result retrieval in the current state of development will always result in an JobResultNotFound error (see [`KubernetesManager.get_job_result()`](./src/pygeoapi_k8s_manager/manager.py)).

**environment variables available**:

| **name** | **comment** |
| --- | --- |
| `PYGEOAPI_JOB_ID` | Each container (normal and init) of the job pod will receive this variable containing the pygeoapi provided id of the current job, e.g. `99755242-31af-11f0-80bd-0255ac10006c`. |

**environment variables to configure**:

| **name**                                            | **comment**                                                                                                                  |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT`    | Endpoint of the bucket hosting service, similar to `FSSPEC_S3_ENDPOINT_URL`, e.g. OTC: `https://obs.eu-de.otc.t-systems.com` |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY`         | The access key with permission to upload files to the given "path", similar to `FSSPEC_S3_KEY`                               |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET`      | The access key secret for the key, similar to `FSSPEC_S3_SECRET`.                                                            |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME`        | Name of the bucket.                                                                                                          |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX` | The "folder" the log files will be uploaded to. It MUST end with an `/`.                                                     |

Ensure, that the bucket is **not publicly** available in the internet, because the logs might leak confidential information and should be consulted only by technical personnel.

⚠️*Hint*:
The controller will cancel the log file upload, if any of these variables is not configured and log errors.

## Development

We are using [uv](https://docs.astral.sh/uv/) to manage the project.

You can use a kind based k8s cluster for testing.
[Install kind following the according instructions](https://kind.sigs.k8s.io/docs/user/quick-start/#installation).
The project specific kind set-up is outlined in [/k8s-kind/](./k8s-kind/README.md).

### Dependency Management with uv

- Add normal dependency: `uv add dependency`
- Add `dev` dependency: `uv add --dev dependency`
- Check if `uv.lock` is up-to-date: `uv lock --check`
- Sync `pyproject.toml` and `uv.lock`: `uv lock`
- Upgrade all dependencies to latest version `uv lock --upgrade`
- Upgrade one specific package: `uv lock --upgrade-package <name>`
- Upgrade local venv: `uv sync`

The docker image installs the project's `[project].dependencies`; pygeoapi itself is provided by the base image and therefore does not need to be reinstalled.

### Increase pygeoapi/project version

Files to adjust:

- `Dockerfile`
- `.github/workflows/build-pipeline.yaml`
- `pyproject.toml`
- `uv.lock`
- `README.md`

- **pygeoapi**

  ```shell
  PYGEOAPI_VERSION=0.24.0
  sed -i "s/^    \"pygeoapi==.*\",/    \"pygeoapi==${PYGEOAPI_VERSION}\",/" pyproject.toml && \
  sed -i "s/^ARG PYGEOAPI_VERSION=.*/ARG PYGEOAPI_VERSION=${PYGEOAPI_VERSION}/" Dockerfile && \
  sed -i "s/^  PYGEOAPI_VERSION: .*/  PYGEOAPI_VERSION: ${PYGEOAPI_VERSION}/" .github/workflows/build-pipeline.yaml && \
  sed -i -E "s/^([[:space:]]*)PYGEOAPI_VERSION=.*/\1PYGEOAPI_VERSION=${PYGEOAPI_VERSION}/" README.md && \
  uv sync --upgrade
  ```

- **pygeoapi-k8s-manager**

  ```shell
  VERSION=0.29
  sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml && \
  sed -i "s/^ARG VERSION=.*/ARG VERSION=${VERSION}/" Dockerfile && \
  sed -i -E "s/^([[:space:]]*)VERSION=.*/\1VERSION=${VERSION}/" README.md && \
  uv sync --upgrade
  ```

### Kubernetes client library version

The Python `kubernetes` client library version is managed as a dependency pin in `pyproject.toml` (e.g. `"kubernetes>=33,<34"`) together with `uv.lock`.
It can be retrieved via `<pygeoapi-context-path>/static/info.txt` (line `kubernetes client: …`).

To adjust it, either upgrade within the current pin range:

```shell
uv lock --upgrade-package kubernetes
```

or move the pin to a new client series and re-lock (example: series 33 → 34):

```shell
sed -i -E 's/"kubernetes>=[0-9]+,<[0-9]+"/"kubernetes>=34,<35"/' pyproject.toml && \
uv lock
```

### Debugging with vscode

The project come with vscode debug launch configuration, that works with the kind cluster configuration.
The details can be found in the two folders in `.vscode/` and `k8s-kind/`.
For debugging, only the minio set-up is required.

## Container

### Known Limitation: Manager Container Hardening

The configurable `securityContext` described above applies to the **spawned job pods**, not to the manager pod itself.
The manager container is **not** hardened (`runAsNonRoot` / `readOnlyRootFilesystem` are not set), because the `geopython/pygeoapi` base image runs as root, binds the privileged port 80, and writes `/pygeoapi/local.openapi.yml` at startup.
Enabling `runAsNonRoot` or `readOnlyRootFilesystem` for the manager would therefore require base-image changes (a non-root UID, a high port, and writable mounts) and is out of scope for this project.

### Commands

**Build** the latest container image with docker using the following command:

```shell
VERSION=0.29
PYGEOAPI_VERSION=0.24.0
REGISTRY=docker.io \
IMAGE=52north/pygeoapi-k8s-manager \
; \
docker build \
  -t "${REGISTRY}/${IMAGE}:latest" \
  -t "${REGISTRY}/${IMAGE}:${VERSION}" \
  --build-arg VERSION="$VERSION" \
  --build-arg PYGEOAPI_VERSION="$PYGEOAPI_VERSION" \
  --build-arg BUILD_DATE=$(date -u --iso-8601=seconds) \
  --build-arg GIT_COMMIT=$(git rev-parse --short=20 -q --verify HEAD) \
  --build-arg GIT_TAG=$(git describe --tags) \
  --build-arg GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD) \
  .
```

**Run** the image locally for testing:

⚠️*Hint*:
Add **a whitespace before the command** to prevent the secrets to be stored in the history of the shell.
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

- **Without local trivy installation**:

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

- **With local trivy installation**:

  ```shell
  trivy image \
      --scanners vuln \
      --format table \
      --severity CRITICAL,HIGH \
      --ignore-unfixed \
      52north/pygeoapi-k8s-manager:latest
  ```

**Vulnerability scanning policy**:

The [CI pipeline](.github/workflows/build-pipeline.yaml) blocks the image push **only** on `CRITICAL`/`HIGH` vulnerabilities that have an available fix (`--ignore-unfixed`).
Such a finding is reported internally to the maintainers.
`MEDIUM`/`LOW` and unfixed vulnerabilities are **deliberately not gated**.
For visibility, every release build publishes a non-blocking full Trivy report (all severities, including unfixed) as the CI artifact `trivy-report-full` (retained 30 days) for periodic or on-demand review.

**Manual upload to registry** after successful docker login:

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

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This work is licensed in [Apache 2.0](./LICENSE).

Create/Update the NOTICE file using the following command **AFTER** building the image:

```shell
./scripts/generate-notice.sh
```

The developments are based on [pygeoapi-kubernetes-papermill](https://github.com/eoxhub-workspaces/pygeoapi-kubernetes-papermill).

## Funding

The development of the "pygeoapi - kubernetes manager" implementation was supported by several organizations and projects.
We would like to thank the following organizations and projects, among others:

| Project/Logo | Description |
| :---: | :--- |
| ![DIRECTED](./img/logo_directed.png) | [DIRECTED](https://52north.org/solutions/directed/) aims to reduce vulnerability to extreme weather events and foster disaster-resilient European societies by promoting interoperability of data, models, communication and governance on all levels and between all actors of the disaster risk management and climate adaptation process. |
| ![I-CISK](./img/logo_i-cisk.png) | [I-CISK](https://52north.org/solutions/i-cisk/) will empower local communities to build and use tailored local Climate Services to adapt to climate change. |
| ![TwinShip](./img/logo_twinship.png) | [TwinShip](https://twin-ship.eu/) aims to reduce Greenhouse Gas emissions in international shipping. It is co-funded by the European Union’s Horizon Europe programme under grant agreement No. 101192583. |
| ![WEB-AIS](./img/logo_web-ais.png) | [WEB-AIS](https://52north.org/solutions/web-based-agricultural-information-system-webais-for-bangladesh/) aims for improving water management in Bangladesh in times of climate change impacts. |
