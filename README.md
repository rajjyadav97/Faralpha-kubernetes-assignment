# FarAlpha SDE Intern Assignment — Flask, MongoDB and Kubernetes

This repository deploys a Python Flask API backed by an authenticated MongoDB StatefulSet on a local Minikube cluster. It includes a persistent MongoDB volume, Services, resource requests/limits and a CPU-based Horizontal Pod Autoscaler (HPA).

> **Important:** Do not report autoscaling numbers or claim screenshots were captured until you run the tests below. Add your real command outputs and screenshots in the `evidence/` folder before submission. The YAML uses example passwords; replace them before applying and do not publish real secrets.

## Architecture

- Flask Deployment: 2 initial replicas, can scale from 2 to 5.
- Flask Service: NodePort `30080` for access from the host.
- MongoDB StatefulSet: 1 pod with authentication enabled.
- MongoDB headless Service: internal DNS and stable StatefulSet network identity; not exposed outside the cluster.
- Persistent storage: StatefulSet `volumeClaimTemplates` requests a 1 GiB PVC mounted at `/data/db`. Minikube's default StorageClass normally provisions the PV automatically.
- HPA: targets average CPU utilization of 70%.
- Both application and database request `200m` CPU / `250Mi` memory and limit `500m` CPU / `500Mi` memory.

## Prerequisites

Install Docker Desktop, kubectl and Minikube on Windows. Ensure Docker Desktop is running and WSL 2 setup is complete if Docker requests it.

Check:
```powershell
docker --version
kubectl version --client
minikube version
```

## 1. Start the cluster and metrics server

```powershell
minikube start --driver=docker
minikube addons enable metrics-server
kubectl get nodes
kubectl top nodes
```

Wait for `kubectl top nodes` to return metrics before testing HPA.

## 2. Set demo credentials and create Kubernetes resources

Edit `k8s/mongodb-secret.example.yaml` and replace both example passwords. This is a learning assignment: for a real repository, create the Secret locally and avoid committing real credentials.

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/mongodb-secret.example.yaml
```

The MongoDB application user must exist in MongoDB. The official Mongo image creates only the root user from `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`. After MongoDB starts, create the least-privilege app user once:

```powershell
kubectl apply -f k8s/mongodb-service.yaml
kubectl apply -f k8s/mongodb-statefulset.yaml
kubectl -n faralpha rollout status statefulset/mongodb --timeout=180s
kubectl -n faralpha exec -it mongodb-0 -- mongosh -u adminuser -p --authenticationDatabase admin
```

Enter the root password at the prompt, then run the following in the Mongo shell, substituting the same app password as in `k8s/flask-config.example.yaml`:

```javascript
use flask_db
db.createUser({
  user: "flaskuser",
  pwd: "change-this-app-password",
  roles: [{ role: "readWrite", db: "flask_db" }]
})
exit
```

For the shell command above, use the actual root username you placed in the Secret. If you use different credential values, keep the URI and created user in sync.

## 3. Build the Flask image

From the repository root, with Docker Desktop running:

```powershell
minikube image build -t faralpha-flask:1.0 .
```

Alternative registry workflow: `docker build -t YOUR_DOCKERHUB_USERNAME/faralpha-flask:1.0 .`, then `docker login`, `docker push YOUR_DOCKERHUB_USERNAME/faralpha-flask:1.0`, and change `image` in `k8s/flask-deployment.yaml` to that pushed image name. Never put registry passwords in source files.

## 4. Configure and deploy Flask

Edit `k8s/flask-config.example.yaml` to use the same app password created in MongoDB. Then apply the resources:

```powershell
kubectl apply -f k8s/flask-config.example.yaml
kubectl apply -f k8s/flask-deployment.yaml
kubectl apply -f k8s/flask-service.yaml
kubectl -n faralpha rollout status deployment/flask-app --timeout=180s
kubectl -n faralpha get pods,svc,pvc
```

## 5. Test endpoints

In one terminal:
```powershell
kubectl -n faralpha port-forward service/flask-service 5000:5000
```

In a second PowerShell terminal:
```powershell
Invoke-RestMethod http://localhost:5000/
Invoke-RestMethod -Method Post -Uri http://localhost:5000/data -ContentType "application/json" -Body '{"sampleKey":"sampleValue","source":"assignment-test"}'
Invoke-RestMethod http://localhost:5000/data
```

Expected: `/` returns a welcome message with a timestamp; POST `/data` returns `status: Data inserted`; GET `/data` returns inserted documents.

## 6. Configure HPA and test autoscaling

```powershell
kubectl apply -f k8s/flask-hpa.yaml
kubectl -n faralpha get hpa
kubectl -n faralpha top pods
```

The HPA requires the Metrics Server and CPU requests on the target containers. It aims for average CPU use of 70% of requested CPU, with replicas bounded between 2 and 5.

Generate traffic from a temporary pod (leave this running in a separate terminal during observation):
```powershell
kubectl -n faralpha run load-generator --image=busybox:1.36 --restart=Never -- sh -c "while true; do wget -q -O- http://flask-service:5000/ >/dev/null; done"
```

Watch HPA and pods in another terminal:
```powershell
kubectl -n faralpha get hpa -w
kubectl -n faralpha get deployment flask-app
kubectl -n faralpha get pods
```

A request loop may not create enough CPU load to trigger scale-out on every computer. If replicas do not increase, inspect `kubectl -n faralpha describe hpa flask-hpa`, `kubectl -n faralpha top pods`, and increase load or use a CPU stress test. HPA scaling takes time and is not instantaneous. Do not invent a scale-out result if the observed CPU never crosses the target.

Stop and remove the load generator:
```powershell
kubectl -n faralpha delete pod load-generator
```

### Autoscaling results (fill with actual results)

Record the values observed on your machine after testing:

| Observation | Actual result |
|---|---|
| Initial Flask replicas | TODO |
| HPA target | 70% CPU |
| Minimum / maximum replicas | 2 / 5 |
| CPU under load | TODO (from `kubectl top pods`) |
| Replicas reached during load | TODO |
| Time to scale out | TODO |
| Replicas after load stopped | TODO |
| Issues encountered | TODO |

### Required screenshots

Create an `evidence/` directory and save genuine screenshots from your machine. Recommended:
1. `01-pods-services-pvc.png` — `kubectl -n faralpha get pods,svc,pvc`
2. `02-endpoints.png` — successful POST and GET requests
3. `03-hpa-under-load.png` — `kubectl -n faralpha get hpa` while load is running
4. `04-replicas-scaled.png` — `kubectl -n faralpha get deployment flask-app` showing the observed replica count
5. `05-pods-cpu.png` — `kubectl -n faralpha top pods`

Do not submit placeholder screenshots as test evidence.

## DNS resolution in Kubernetes

Kubernetes creates DNS records for Services. Pods in the `faralpha` namespace can reach the Flask Service using `flask-service` and MongoDB using the stable StatefulSet DNS name `mongodb-0.mongodb.faralpha.svc.cluster.local`. The `mongodb` headless Service and StatefulSet identity provide stable pod DNS. The MongoDB Service is cluster-internal; it is not exposed via NodePort or LoadBalancer. The Flask `MONGODB_URI` uses the internal DNS name and `authSource=admin` because the initial root account is created in MongoDB's `admin` database.

## Resource requests and limits

- **Requests** are used by the Kubernetes scheduler to place pods and by CPU-based HPA utilization calculations as the baseline.
- **Limits** cap resource consumption. CPU over the limit is throttled; memory over the limit can lead to an out-of-memory kill.
- This assignment uses `requests: cpu=200m, memory=250Mi` and `limits: cpu=500m, memory=500Mi` for both Flask and MongoDB as the requested sample values. These are demonstration values and should be tuned for production workloads.

## Design choices

- Flask runs under Gunicorn instead of Flask's development server, which is not intended for production use.
- MongoDB uses a StatefulSet and persistent volume claim so its pod identity and data volume survive pod replacement.
- MongoDB is internal-only through a headless Service; Flask is exposed with NodePort for local access. Port-forwarding is also provided as a convenient local test method.
- MongoDB authentication uses Kubernetes Secret references for root credentials. The example file is for local practice only; production systems should use a secret manager and stronger operational controls.
- HPA uses `autoscaling/v2`, CPU utilization target 70%, minimum 2 and maximum 5 replicas. Metrics Server is required.
- A single MongoDB replica is suitable for this local assignment, not high availability. Production would need a carefully designed replica set, backups, TLS, network policies and secret rotation.

## Troubleshooting

- `ImagePullBackOff`: confirm `minikube image build -t faralpha-flask:1.0 .` succeeded and image name matches.
- HPA shows `<unknown>`: enable Metrics Server and wait; check `kubectl top pods`.
- MongoDB auth failure: ensure app username/password match the user created in MongoDB and the URI has `authSource=admin`.
- PVC pending: check `kubectl -n faralpha get pvc` and `kubectl get storageclass`.
- App readiness failing: inspect `kubectl -n faralpha logs deployment/flask-app` and `kubectl -n faralpha describe pod <pod-name>`.

## Cleanup

```powershell
kubectl delete namespace faralpha
minikube stop
```

## Autoscaling Test Results

### Configuration
- Minimum replicas: 2
- Maximum replicas: 5
- CPU utilization target: 70%
- Metrics Server: Enabled

### Test Procedure
A temporary load-generator pod sent repeated HTTP GET requests to the Flask service to generate traffic. HPA metrics and replica counts were monitored using kubectl.

### Observed Results
During the load test, CPU utilization reached 93%, 100%, and 80%. The HPA increased the Flask deployment from 2 replicas to 3 and then 4 replicas. After the load was stopped, CPU utilization decreased to 15% and later to 1%.

The load-generator pod was deleted after testing.

### Application and Storage Verification
- Flask welcome endpoint returned the current timestamp.
- POST request to `/data` returned `Data inserted`.
- Flask pods and MongoDB pod were Running.
- MongoDB persistent volume claim was Bound with 1 GiB capacity.

### Evidence
Add the actual screenshots below:
- HPA watch output showing CPU utilization and replica scaling.
- Final `kubectl get pods -n faralpha` output.
- Final `kubectl get pvc -n faralpha` output.
<img width="1600" height="900" alt="hpa-autoscaling2" src="https://github.com/user-attachments/assets/a64aab6c-e87a-4914-b91d-f2771ef61fdd" />
<img width="1600" height="900" alt="hpa-autoscaling2" src="https://github.com/user-attachments/assets/4c2f0ddb-b840-42b3-9f1c-c6fb7d055a10" />
<img width="1600" height="900" alt="hpa-autoscaling png" src="https://github.com/user-attachments/assets/3de324ee-d655-412c-aa90-e28f565b92d4" />

