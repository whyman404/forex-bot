###############################################################################
# infra/terraform/main.tf
#
# Phase 1 / MVP target topology:
#
#   - Linux VPS on Hetzner Cloud (HEL1 region — close to EU brokers).
#     Runs docker compose: backend, frontend, postgres, redis, prometheus,
#     grafana, loki, promtail, trading-engine.
#   - Cloudflare DNS (forex-bot.app) + Cloudflare Tunnel for public access.
#     No public ingress on the VPS itself — Tunnel handles TLS + DDoS.
#   - Cloudflare R2 bucket for Postgres backups (WAL + nightly dump).
#   - Windows VPS for MT5: provisioned MANUALLY on Contabo for Phase 1.
#     See `infra/scripts/setup-windows-vps.md`. When we move to AWS EC2 we
#     will switch the `windows_vps` module to the `aws_instance` resource —
#     placeholder block is at the bottom of this file.
#
# State backend: Cloudflare R2 (S3-compatible). Set TF_STATE_R2_* env vars.
#
# This is a sketch — it bootstraps. Production should split into modules:
#   modules/linux-vps/, modules/dns/, modules/backups/.
###############################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state on R2 (S3 protocol). Bootstrap once with local state, then migrate.
  backend "s3" {
    bucket                      = "forex-bot-tfstate"
    key                         = "prod/terraform.tfstate"
    region                      = "auto"
    endpoints                   = { s3 = "https://<account>.r2.cloudflarestorage.com" }
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
  }
}

###############################################################################
# Variables
###############################################################################
variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "cloudflare_account_id" {
  type = string
}

variable "domain" {
  type    = string
  default = "forex-bot.app"
}

variable "linux_server_type" {
  type        = string
  default     = "cpx31" # 4 vCPU, 8 GB RAM — fits Phase 1 stack
  description = "Hetzner server type. cpx31 ~ $15/mo."
}

variable "linux_location" {
  type    = string
  default = "hel1"
}

variable "ssh_public_key" {
  type        = string
  description = "Admin SSH key (you, plus break-glass key from 1password)."
}

variable "alert_email" {
  type    = string
  default = "whyman404@gmail.com"
}

###############################################################################
# Providers
###############################################################################
provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

###############################################################################
# Linux VPS — application host
###############################################################################
resource "hcloud_ssh_key" "admin" {
  name       = "forex-bot-admin"
  public_key = var.ssh_public_key
}

resource "hcloud_firewall" "linux_fw" {
  name = "forex-bot-linux-fw"

  # SSH (lock to ops bastion IP in real life; here we allow Cloudflare WARP IPs).
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0"] # TODO: restrict to ops bastion
  }

  # Cloudflare Tunnel is outbound only — no public HTTP/HTTPS ports needed.
}

resource "hcloud_server" "linux" {
  name         = "forex-bot-linux-01"
  server_type  = var.linux_server_type
  location     = var.linux_location
  image        = "debian-12"
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.linux_fw.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    cloudflare_tunnel_token = random_password.tunnel_placeholder.result
  })

  labels = {
    role = "app"
    env  = "prod"
  }

  lifecycle {
    # Disk + volume changes must be explicit, never accidental.
    prevent_destroy = true
  }
}

resource "hcloud_volume" "data" {
  name      = "forex-bot-data"
  size      = 50 # GB — pg + loki together
  location  = var.linux_location
  format    = "ext4"
  automount = false

  lifecycle { prevent_destroy = true }
}

resource "hcloud_volume_attachment" "data" {
  volume_id = hcloud_volume.data.id
  server_id = hcloud_server.linux.id
  automount = true
}

###############################################################################
# Cloudflare DNS
###############################################################################
data "cloudflare_zone" "this" {
  name = var.domain
}

resource "cloudflare_record" "app" {
  zone_id = data.cloudflare_zone.this.id
  name    = "app"
  type    = "CNAME"
  value   = "${cloudflare_tunnel.app.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}

resource "cloudflare_record" "api" {
  zone_id = data.cloudflare_zone.this.id
  name    = "api"
  type    = "CNAME"
  value   = "${cloudflare_tunnel.app.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}

###############################################################################
# Cloudflare Tunnel — public access without opening ports on the VPS
###############################################################################
resource "random_password" "tunnel_placeholder" {
  length  = 64
  special = false
}

resource "cloudflare_tunnel" "app" {
  account_id = var.cloudflare_account_id
  name       = "forex-bot-app"
  secret     = base64encode(random_password.tunnel_placeholder.result)
}

resource "cloudflare_tunnel_config" "app" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_tunnel.app.id

  config {
    ingress_rule {
      hostname = "app.${var.domain}"
      service  = "http://localhost:3000"
    }
    ingress_rule {
      hostname = "api.${var.domain}"
      service  = "http://localhost:8000"
    }
    ingress_rule {
      # default fallback
      service = "http_status:404"
    }
  }
}

###############################################################################
# R2 bucket for backups
###############################################################################
resource "cloudflare_r2_bucket" "backups" {
  account_id = var.cloudflare_account_id
  name       = "forex-bot-backups"
  location   = "WEUR"
}

# Lifecycle: 30-day retention is enforced by the backup script. R2 itself
# doesn't have built-in lifecycle policy on free tier — script handles it.

###############################################################################
# Windows VPS placeholder
###############################################################################
# Contabo lacks a mature Terraform provider, so Phase 1 buys the Windows VPS
# through the web UI. Track its metadata here for documentation purposes.
#
# When we migrate to AWS EC2 Windows for HA, replace this comment block
# with an `aws_instance` resource:
#
# resource "aws_instance" "mt5_supervisor" {
#   ami                    = data.aws_ami.windows_server_2022.id
#   instance_type          = "t3.small"
#   key_name               = aws_key_pair.admin.key_name
#   vpc_security_group_ids = [aws_security_group.mt5_sg.id]
#   user_data              = file("${path.module}/mt5-userdata.ps1")
#   tags                   = { Name = "forex-bot-mt5-01", role = "mt5-supervisor" }
# }
#
locals {
  windows_vps_provisioned_manually = {
    provider     = "Contabo"
    plan         = "VPS S Windows"
    region       = "EU"
    cost_per_mo  = "~$11"
    setup_doc    = "infra/scripts/setup-windows-vps.md"
    inventory_at = "ops/inventory.yaml (private repo)"
  }
}

###############################################################################
# Outputs
###############################################################################
output "linux_ipv4" {
  value = hcloud_server.linux.ipv4_address
}

output "tunnel_id" {
  value = cloudflare_tunnel.app.id
}

output "r2_bucket" {
  value = cloudflare_r2_bucket.backups.name
}

output "windows_vps_notes" {
  value = local.windows_vps_provisioned_manually
}
