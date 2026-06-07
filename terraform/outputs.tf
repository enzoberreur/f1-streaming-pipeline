output "app_public_ip" {
  description = "Public IP of the application/monitoring server."
  value       = aws_instance.app.public_ip
}

output "grafana_url" {
  description = "Grafana dashboards."
  value       = "http://${aws_instance.app.public_ip}:3000"
}

output "airflow_url" {
  description = "Airflow web UI."
  value       = "http://${aws_instance.app.public_ip}:8080"
}

output "prometheus_url" {
  description = "Prometheus."
  value       = "http://${aws_instance.app.public_ip}:9090"
}

output "database_endpoint" {
  description = "PostgreSQL endpoint (private)."
  value       = aws_db_instance.postgres.address
}

output "ssh_command" {
  description = "SSH into the server."
  value       = "ssh ubuntu@${aws_instance.app.public_ip}"
}
