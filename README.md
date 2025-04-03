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

- Required RBAC rules:

  ```shell
    Resources    Non-Resource URLs  Resource Names  Verbs
  ---------    -----------------  --------------  -----
  jobs.batch   []                 []              [get list watch create update patch delete]
  events       []                 []              [get watch list]
  pods/log     []                 []              [get watch list]
  pods/status  []                 []              [get watch list]
  pods         []                 []              [get watch list]
  ```

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
VERSION=0.5 \
REGISTRY=docker.io \
IMAGE=52north/pygeoapi-k8s-manager \
; \
docker build \
  -t "${REGISTRY}/${IMAGE}:latest" \
  -t "${REGISTRY}/${IMAGE}:${VERSION}" \
  --build-arg BUILD_DATE=$(date -u --iso-8601=seconds) \
  --build-arg GIT_COMMIT=$(git rev-parse --short=12 -q --verify HEAD) \
  --build-arg GIT_TAG=$(git describe --tags) \
  --build-arg GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD) \
  .
```

**Run** the image locally for testing:

```shell
REGISTRY=docker.io \
IMAGE=52north/pygeoapi-k8s-manager \
docker run \
  --env PYGEOAPI_K8S_MANAGER_NAMESPACE=default \
  --env PYGEOAPI_K8S_MANAGER_API_TOKEN=token \
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
- [ ] Implement job result subscriber workflow:
  - [updater thread](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L122-L128)
  - [According code](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L531-L596)
- [ ] Implement injecting pod lifetime configuration, atm. 100 days too long for e.g. GPU pods
- [ ] Are Pygeoapi Start and K8s Job/POD Start Time not the same? Should they be mapped by OGC Created and Started?
- [ ] Why are the `jobControlOptions` from hello_world_k8s and generic_image not honoured?
