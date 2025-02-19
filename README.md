# pygeoapi - kubernetes manager

Extends [pygeoapi](https://pygeoapi.io/) by a manager for kubernetes jobs and a process to execute any container image on a cluster.

It implements the following features and workflow.


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

## Container

Build the latest container image with docker using the following command:

```shell
IMAGE=52north/pygeoapi-k8s-manager VERSION=0.1; docker build -t "${IMAGE}:latest" -t "${IMAGE}:${VERSION}" --build-arg GIT_COMMIT=$(git rev-parse -q --verify HEAD) --build-arg BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ") .
```

## Tests


## ToDos

- [ ] Implement job result subscriber workflow:
      - [updater thread](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L122-L128)
      - [According code](https://github.com/eurodatacube/pygeoapi-kubernetes-papermill/blob/main/pygeoapi_kubernetes_papermill/kubernetes.py#L531-L596)
