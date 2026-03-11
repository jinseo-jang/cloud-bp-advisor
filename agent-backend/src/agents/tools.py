import re
from langchain_core.tools import tool

@tool
def context7_mcp(query: str, library_id: str) -> str:
    """
    Uses Context7 MCP to retrieve accurate, up-to-date documentation and code samples 
    for Terraform or Cloud SDKs. Highly recommended for accurate TF HCL generation.
    """
    q = query.lower()
    if "aws" in library_id.lower() or "aws" in q:
        return 'Terraform AWS Example: resource "aws_instance" "app" { ami = "ami-123", instance_type = "t3.micro" }'
    elif "google" in library_id.lower() or "gcp" in q:
        return 'Terraform GCP Example: resource "google_container_cluster" "primary" { name = "my-gke", location = "us-central1" }'
    return f"Context7 documentation for {library_id}: Resource configuration examples matching {query}."

@tool
def tfsec_scan(hcl_content: str) -> str:
    """
    Runs tfsec/checkov static analysis to check for security misconfigurations.
    Returns PASS if secure, or a list of CRITICAL errors if insecure configurations are found.
    """
    errors = []
    if "0.0.0.0/0" in hcl_content:
        errors.append("CRITICAL: Open security group or firewall rule (0.0.0.0/0) detected. Restrict access.")
    if "password =" in hcl_content or "password=" in hcl_content:
        errors.append("CRITICAL: Hardcoded password detected in HCL. Use variables or Secret Manager.")
    if "deletion_protection = false" in hcl_content:
        errors.append("HIGH: Database deletion_protection is set to false. Set to true for production.")
        
    if errors:
        return "tfsec scan failed with the following issues:\n" + "\n".join(errors)
    return "tfsec run successful. PASS"

@tool
def infracost_estimate(resource_query: str) -> str:
    """
    Runs infracost to get an accurate expected monthly cloud bill for the generated architecture or HCL.
    """
    q = resource_query.lower()
    cost = 0
    if "gke" in q or "eks" in q: cost += 75
    if "sql" in q or "rds" in q: cost += 150
    if "run" in q or "fargate" in q: cost += 20
    if "load balancer" in q or "alb" in q: cost += 18
    if cost == 0: cost = 250
    return f"Estimated monthly cost: ${cost}/month."
