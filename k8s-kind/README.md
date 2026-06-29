# Local test with kind

Kind documentation: <https://kind.sigs.k8s.io/>

## Create Kubernetes cluster

Switch to `k8s-kind`:

```shell
cd ./k8s-kind
```

Create cluster:

```shell
k8s-kind/$ kind create cluster --config kind-cluster.yaml
```

Check cluster:

```shell
k8s-kind/$ kubectl cluster-info --context kind-pygeoapi-k8s-manager
```

## Prepare Docker Image(s)

Build docker image as [outlined in the documentation](../README.md#container), but set the image tag `latest` to `local`:

```shell
k8s-kind/$ docker tag 52north/pygeoapi-k8s-manager:latest 52north/pygeoapi-k8s-manager:local
```

[Load docker image](https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-your-cluster) into kind cluster:

```shell
k8s-kind/$ kind load docker-image --name pygeoapi-k8s-manager 52north/pygeoapi-k8s-manager:local
```

### Pull and Load Demo Use Case Images

You can ignore these steps, if always have a good internet connection.
This will pull the images not only into the temporary kind control plane not, but in your local docker engine, too.

Pull the images to your local engine:

```shell
echo "quay.io/minio/minio:latest
      quay.io/minio/mc:latest
      docker.io/bash:latest
      docker.io/busybox:latest" | \
      xargs -P10 -n1 docker pull
```

Load images into temporal kind control plane node:

```shell
echo "quay.io/minio/minio:latest
      quay.io/minio/mc:latest
      docker.io/bash:latest
      docker.io/busybox:latest" | \
      xargs -P10 -n1 kind load docker-image --name pygeoapi-k8s-manager
```

### Kind image management (for debugging)

Check available images:

```shell
k8s-kind/$ docker exec -it pygeoapi-k8s-manager-control-plane crictl images | head -n3
```

Delete image:

```shell
k8s-kind/$ docker exec -it pygeoapi-k8s-manager-control-plane crictl rmi \
  $(\
    docker exec -it pygeoapi-k8s-manager-control-plane crictl images \
    | grep --color=never pygeoapi-k8s-manager \
    | awk '{print $3}'\
  )
```

## Run containers

Apply k8s manifests:

```shell
k8s-kind/$ kubectl apply -k .
```

## Create Bucket in Minio

*Here*: This is not required, if the according job `minio-bucket-init` is executed successfully.

1. Open <http://localhost:30100/>.

1. Use credentials from [minio set-up](minio.yaml) and log-in.

1. Create a new bucket with name `test-bucket` by clicking on "Create Bucket" on the left.

1. Select the newly created bucket and "create [a] new path" called `k8s-manager/logs/`.

## Test application

Visit pygeoapi at <http://localhost:30080/pygeoapi/>

Execute the "hello world" process **synchronous**:

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

or **asynchronous**:

```shell
curl -v -X 'POST' \
  'http://localhost:30080/pygeoapi/processes/hello-world-k8s/execution' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Prefer: respond-async' \
  -d '{
        "inputs": {
          "message": "Am I in TV, now?",
          "name": "John Doe"
        }
      }'
```

Generic Image Processor with different types:

```shell
curl -v -X 'POST' \
  'http://localhost:30080/pygeoapi/processes/generic-image-processor-example/execution' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Prefer: respond-async' \
  -d '{
        "inputs": {
          "token": "do_not_use_in_production",
          "test-string": "this is my test-string",
          "test-boolean": true,
          "test-integer": -272,
          "test-number": 19.2340
        }
      }'
```

## Remove cluster

Execute the following command to clean-up the cluster and its configuration:

```shell
kind delete cluster --name pygeoapi-k8s-manager
```
