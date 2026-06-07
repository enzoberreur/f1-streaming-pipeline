# Terraform - Cloud Infrastructure as Code

Provisions the Ferrari F1 IoT data infrastructure on AWS:

- **VPC** with two public subnets (multi-AZ), internet gateway and routing
- **EC2** Ubuntu server that bootstraps Docker and runs the full stack
  (simulator, stream-processor, Prometheus, Grafana, Airflow) via `user_data.sh`
- **RDS PostgreSQL** - the managed, encrypted, private historical/analytical
  store for telemetry (data model in [`../sql`](../sql))
- **Security groups** - dashboards/SSH restricted to your IP; the database is
  reachable only from the app server

```
terraform/
├── versions.tf      required Terraform + provider versions
├── provider.tf      AWS provider + default tags
├── variables.tf     inputs (region, sizes, CIDRs, db credentials)
├── network.tf       VPC, subnets, IGW, routing, security groups, db subnet group
├── compute.tf       EC2 app/monitoring server (+ AMI lookup)
├── database.tf      RDS PostgreSQL
├── outputs.tf       public IP, dashboard URLs, db endpoint
├── user_data.sh     cloud-init: install Docker + run the stack
└── terraform.tfvars.example
```

## Prerequisites

- Terraform >= 1.5, AWS credentials (`aws configure` or `AWS_*` env vars)
- An existing EC2 key pair (for SSH)

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

Outputs include the Grafana/Airflow/Prometheus URLs and the SSH command. After
~2-3 minutes (cloud-init pulls images and starts the stack), open the Grafana URL.

## Teardown

```bash
terraform destroy
```

## Notes

- `db_password` is sensitive; pass it via `TF_VAR_db_password` or `terraform.tfvars`
  (gitignored). State files and tfvars are gitignored; use a remote backend
  (S3 + DynamoDB lock) for team use.
- For a local / on-premise deployment use the Docker Compose stack at the repo
  root (`make start`) or the Kubernetes manifests in [`../k8s`](../k8s).
- CI runs `terraform fmt -check` and `terraform validate` on every push
  (`.github/workflows/ci-cd.yml`).
