# Local test with kind

Kind documentation: <https://kind.sigs.k8s.io/>

## Create Kubernetes cluster

Create cluster:

```shell
kind create cluster --config kind-cluster.yaml
```

Check cluster:

```shell
kubectl cluster-info --context kind-pygeoapi-k8s-manager
```

## Prepare Docker Image

Build docker image as [outlined in the documentation](../README.md#container), but set `VERSION` to `local`.

[Load docker image](https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-your-cluster) into kind cluster:

```shell
kind load docker-image --name pygeoapi-k8s-manager 52north/pygeoapi-k8s-manager:local
```

### Kind image management (for debugging)

Check available images:

```shell
docker exec -it pygeoapi-k8s-manager-control-plane crictl images
```

Delete image:

```shell
docker exec -it pygeoapi-k8s-manager-control-plane crictl rmi <id>
```

## Run containers

Apply k8s manifests:

```shell
k8s-kind/$ kubectl apply -k .
```

## Test application

Visit pygeoapi at <http://localhost:30080/pygeoapi/>

Execute the "hello world" process:

```shell
curl -v -X 'POST' \
  'http://localhost:30080/pygeoapi/processes/hello-world-k8s/execution' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "inputs": {
    "message": "Am I in TV, now?",
    "name": "John Doe"
  }
}'
```

## Remove cluster

Execute the following command to clean-up the cluster and its configuration:

```shell
kind delete cluster --name pygeoapi-k8s-manager
```
