# pygeoapi - kubernetes manager

Extends [pygeoapi](https://pygeoapi.io/) by a manager for kubernetes jobs and a process to execute any container image on a cluster.

It implements the following features and workflow.

## Usage

### GenericImageProcessor

The required and supported configuration options are outlined in the example configuration `pygeoapi-config.yaml`.

The given inputs are injected into the k8s job pod via the environment variable `PYGEOAPI_K8S_MANAGER_INPUTS`.
Hence, your process wrapper MUST use this variable for dynamic inputs.
Static inputs can be injected using your environment variable definitions.

Each execution of a GenericImageProcessor requires an auth token to be provided as input `token`.
It MUST match the value of the environment variable `PYGEOAPI_K8S_MANAGER_API_TOKEN`.
An `ProcessorExecuteError` will be raised if not given and matching.

## k8s Configuration Requirements

Required RBAC rules:

```shell
  Resources    Non-Resource URLs  Resource Names  Verbs
---------    -----------------  --------------  -----
jobs.batch   []                 []              [get list watch create update patch delete]
events       []                 []              [get watch list]
pods/log     []                 []              [get watch list]
pods/status  []                 []              [get watch list]
pods         []                 []              [get watch list]
```

See [k8s manifest examples](./k8s-manifests/) for an example set-up, that needs adjustment to your cluster.
The set-up requires a secret `k8s-job-manager` with key `token` in the same namespace of the deployment (*here*: `default`), that could be created with the following command:

```shell
kubectl create secret generic -n default k8s-job-manager --from-literal=token=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 32; echo)
```

## Job Logs Finalizer

The manager comes with an built-in [k8s finalizer](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) controller to handle the logs of the jobs and persist them in an s3 bucket.
The according configuration requires the following environment variables and activation in the pygeoapi configuration.

**pygeoapi configuration snippet**:

```yaml
server:
  manager:
    name: pygeoapi_kubernetes_manager.manager.KubernetesManager
    finalizer_controller: true
```

**environment variables to configure**:

| **name** | **comment** |
|---|---|
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_ENDPOINT` | Endpoint to the bucket hosting service, similar to `FSSPEC_S3_ENDPOINT_URL`, e.g. OTC: `https://obs.eu-de.otc.t-systems.com` |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_KEY` | The access key with permission to upload files to the given "path", similar to `FSSPEC_S3_KEY` |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_SECRET` | The access key secret for the key, similar to `FSSPEC_S3_SECRET`. |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_NAME` | Name of the bucket. |
| `PYGEOAPI_K8S_MANAGER_FINALIZER_BUCKET_PATH_PREFIX` | The "folder" the log files will be uploaded to. It MUST end with an `/`. |

Ensure, that the bucket is not publicly available in the internet, because the logs might leak confidential information and should be consulted only by technical personnel.

*Hint*: The controller will cancel the log file upload, if any of these variables is not configured and log errors. This will result in k8s resources not being deleted!

## Development

Create python venv to develop via `python -m venv --prompt pygeoapi-k8s-manager .venv`

We are using a kind based k8s cluster for testing.
[Install kind following the according instructions](https://kind.sigs.k8s.io/docs/user/quick-start/#installation).

## License

This work is licensed in [Apache 2.0](./LICENSE).

Create/Update the NOTICE file using the following command **AFTER** building the image:

```shell
docker run \
  --rm \
  --entrypoint "/bin/bash" \
  52north/pygeoapi-k8s-manager/pygeoapi-k8s-manager:latest \
  -c "pip install --no-warn-script-location --no-cache-dir pip-licenses > /dev/null && /usr/local/bin/pip-licenses -f plain | grep -v pygeoapi-k8s-manager"
```

## Container

**Build** the latest container image with docker using the following command:

```shell
VERSION=0.9 \
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
Notice the whitespace before the command to prevent the secrets to be stored in the history of the shell.
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
docker push --all-tags 52north//pygeoapi-k8s-manager
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
pip install --upgrade -r requirements-dev.txt
```

## ToDos

- [x] Switch to "stable" release 0.20
- [x] Implement env support
- [x] Implement resource support
- [x] Implement storage support
- [x] Provide inputs via env variable `PYGEOAPI_K8S_MANAGER_INPUTS` "to image"
- [x] Add/document role with required permissions with service account, rolebinding
- [x] Add minimal set of k8s manifests required
- [ ] Implement job result subscriber workflow:
  - [updater thread](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L122-L128)
  - [According code](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L531-L596)
- [ ] Implement injecting pod lifetime configuration, atm. 100 days too long for e.g. GPU pods
- [ ] Are Pygeoapi Start and K8s Job/POD Start Time not the same? Should they be mapped by OGC Created and Started?
- [ ] Why are the `jobControlOptions` from hello_world_k8s and generic_image not honoured?
