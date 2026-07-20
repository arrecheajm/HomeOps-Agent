#!/usr/bin/env bash
set -u

json_string() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read().rstrip("\n")))' 2>/dev/null
}

json_bool() {
  case "$1" in
    true|True|1|yes|Yes) printf 'true' ;;
    *) printf 'false' ;;
  esac
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

safe_number() {
  if [ -n "${1:-}" ]; then
    printf '%s' "$1"
  else
    printf '0'
  fi
}

collected_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
server_id="${HOMEOPS_SERVER_ID:-$(hostname -s 2>/dev/null || hostname)}"
role="${HOMEOPS_ROLE:-unknown}"
host_name="$(hostname -f 2>/dev/null || hostname)"
kernel="$(uname -r)"
architecture="$(uname -m 2>/dev/null || printf 'unknown')"
cpu_model="$(awk -F: '/model name/ {gsub(/^ /, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)"
if [ -z "$cpu_model" ] && command_exists lscpu; then
  cpu_model="$(lscpu 2>/dev/null | awk -F: '/Model name/ {gsub(/^ /, "", $2); print $2; exit}')"
fi
if [ -z "$cpu_model" ]; then
  cpu_model="unknown"
fi
virtualization="unknown"
if command_exists systemd-detect-virt; then
  virtualization="$(systemd-detect-virt 2>/dev/null)"
  if [ -z "$virtualization" ]; then
    virtualization="none"
  fi
fi

os_name="Ubuntu"
os_version="unknown"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  os_name="${NAME:-Ubuntu}"
  os_version="${VERSION_ID:-unknown}"
fi

uptime_seconds="$(cut -d. -f1 /proc/uptime 2>/dev/null || printf '0')"
load_1m="$(awk '{print $1}' /proc/loadavg 2>/dev/null || printf '0')"
cpu_count="$(nproc 2>/dev/null || printf '0')"
memory_total_mb="$(awk '/MemTotal:/ { printf "%.0f", $2 / 1024 }' /proc/meminfo 2>/dev/null)"

memory_used_percent="$(awk '
  /MemTotal:/ { total=$2 }
  /MemAvailable:/ { available=$2 }
  END {
    if (total > 0) {
      printf "%.1f", ((total - available) / total) * 100
    } else {
      printf "0"
    }
  }
' /proc/meminfo 2>/dev/null)"

swap_used_percent="$(awk '
  /SwapTotal:/ { total=$2 }
  /SwapFree:/ { free=$2 }
  END {
    if (total > 0) {
      printf "%.1f", ((total - free) / total) * 100
    } else {
      printf "0"
    }
  }
' /proc/meminfo 2>/dev/null)"

disk_json="$(
  df -P -BG -x tmpfs -x devtmpfs -x squashfs -x efivarfs 2>/dev/null | awk '
    NR > 1 {
      mount=$6
      size=$2
      used=$5
      free=$4
      gsub("%", "", used)
      gsub("G", "", free)
      gsub("G", "", size)
      if (count > 0) {
        printf ","
      }
      printf "{\"mount\":\"%s\",\"used_percent\":%s,\"free_gb\":%s,\"size_gb\":%s}", mount, used, free, size
      count++
    }
  '
)"

pending_total=0
pending_security=0
if command_exists apt; then
  pending_total="$(apt list --upgradable 2>/dev/null | awk 'NR > 1 { count++ } END { print count + 0 }')"
  pending_security="$(apt list --upgradable 2>/dev/null | awk 'NR > 1 && /security|UbuntuESM|esm-apps|esm-infra/ { count++ } END { print count + 0 }')"
fi

reboot_required=false
if [ -f /var/run/reboot-required ]; then
  reboot_required=true
fi

if [ -n "${HOMEOPS_SERVICES:-}" ]; then
  service_names="$HOMEOPS_SERVICES"
else
  case "$role" in
    openvpn_server)
      service_names="ssh sshd openvpnas openvpn openvpn-server@server"
      ;;
    ispy_server)
      service_names="ssh sshd AgentDVR agent-dvr"
      ;;
    container_host)
      service_names="ssh sshd docker"
      ;;
    *)
      service_names="ssh sshd docker openvpn openvpn-server@server openvpnas AgentDVR agent-dvr"
      ;;
  esac
fi
services_json=""
for service in $service_names; do
  if systemctl list-unit-files "$service.service" >/dev/null 2>&1 || systemctl status "$service" >/dev/null 2>&1; then
    state="$(systemctl is-active "$service" 2>/dev/null)"
    if [ -z "$state" ]; then
      state="unknown"
    fi
    enabled_raw="$(systemctl is-enabled "$service" 2>/dev/null)"
    if [ -z "$enabled_raw" ]; then
      enabled_raw="false"
    fi
    enabled=false
    if [ "$enabled_raw" = "enabled" ]; then
      enabled=true
    fi
    name_json="$(printf '%s' "$service" | json_string)"
    state_json="$(printf '%s' "$state" | json_string)"
    if [ -n "$services_json" ]; then
      services_json="$services_json,"
    fi
    services_json="$services_json{\"name\":$name_json,\"state\":$state_json,\"enabled\":$(json_bool "$enabled")}"
  fi
done

docker_installed=false
containers_total=0
containers_running=0
docker_unhealthy_json=""
docker_inventory_collected=false
docker_containers_json='[]'
if command_exists docker; then
  docker_installed=true
  if docker info >/dev/null 2>&1; then
    containers_total="$(docker ps -a --format '{{.Names}}' 2>/dev/null | wc -l | awk '{print $1}')"
    containers_running="$(docker ps --format '{{.Names}}' 2>/dev/null | wc -l | awk '{print $1}')"
    while IFS='|' read -r container_name container_status; do
      [ -n "$container_name" ] || continue
      name_json="$(printf '%s' "$container_name" | json_string)"
      status_json="$(printf '%s' "$container_status" | json_string)"
      if [ -n "$docker_unhealthy_json" ]; then
        docker_unhealthy_json="$docker_unhealthy_json,"
      fi
      docker_unhealthy_json="$docker_unhealthy_json{\"name\":$name_json,\"status\":$status_json}"
    done < <(docker ps --filter health=unhealthy --format '{{.Names}}|{{.Status}}' 2>/dev/null)

    container_ids="$(docker ps -aq 2>/dev/null || true)"
    if [ -z "$container_ids" ]; then
      docker_inventory_collected=true
    else
      # Only emit explicitly allowlisted fields. Environment values, labels other
      # than Compose identity, logs, and container configuration are discarded.
      # shellcheck disable=SC2086
      if docker_containers_json="$(
        docker inspect $container_ids 2>/dev/null | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
containers = []
for item in payload:
    config = item.get("Config") or {}
    state = item.get("State") or {}
    host = item.get("HostConfig") or {}
    labels = config.get("Labels") or {}
    ports = []
    for container_port, bindings in sorted(
        ((item.get("NetworkSettings") or {}).get("Ports") or {}).items()
    ):
        if not bindings:
            ports.append(
                {
                    "container_port": str(container_port),
                    "host_ip": "",
                    "host_port": "",
                }
            )
            continue
        for binding in bindings:
            binding = binding or {}
            ports.append(
                {
                    "container_port": str(container_port),
                    "host_ip": str(binding.get("HostIp") or ""),
                    "host_port": str(binding.get("HostPort") or ""),
                }
            )
    mounts = []
    for mount in item.get("Mounts") or []:
        mounts.append(
            {
                "type": str(mount.get("Type") or "unknown"),
                "source": str(mount.get("Source") or "unknown"),
                "destination": str(mount.get("Destination") or "unknown"),
                "read_only": not bool(mount.get("RW")),
            }
        )
    health = state.get("Health") or {}
    containers.append(
        {
            "name": str(item.get("Name") or "").lstrip("/") or "unknown",
            "image": str(config.get("Image") or item.get("Image") or "unknown"),
            "state": str(state.get("Status") or "unknown"),
            "health": str(health.get("Status") or "none"),
            "restart_policy": str(
                (host.get("RestartPolicy") or {}).get("Name") or "unknown"
            ),
            "network_mode": str(host.get("NetworkMode") or "unknown"),
            "compose_project": str(
                labels.get("com.docker.compose.project") or ""
            ),
            "compose_service": str(
                labels.get("com.docker.compose.service") or ""
            ),
            "ports": ports,
            "mounts": mounts,
        }
    )
print(json.dumps(sorted(containers, key=lambda value: value["name"])))
'
      )"; then
        docker_inventory_collected=true
      else
        docker_containers_json='[]'
      fi
    fi
  fi
fi

failed_ssh_logins_24h=0
successful_ssh_logins_24h=0
if command_exists journalctl; then
  failed_ssh_logins_24h="$(journalctl -u ssh -u sshd --since '24 hours ago' --no-pager 2>/dev/null | grep -ci 'Failed password' || true)"
  successful_ssh_logins_24h="$(journalctl -u ssh -u sshd --since '24 hours ago' --no-pager 2>/dev/null | grep -ci 'Accepted ' || true)"
fi

last_login_summary=""
if command_exists last; then
  last_login_summary="$(
    last -n 3 -w 2>/dev/null | awk '
      NF >= 3 && $1 != "wtmp" {
        user=$1
        source=$3
        if (source == ":0" || source == "tty1") {
          source="local"
        }
        if (count > 0) {
          printf ","
        }
        gsub(/"/, "\\\"", user)
        gsub(/"/, "\\\"", source)
        printf "\"%s from %s\"", user, source
        count++
      }
    '
  )"
fi

cat <<JSON
{
  "schema_version": "1.0",
  "server_id": $(printf '%s' "$server_id" | json_string),
  "role": $(printf '%s' "$role" | json_string),
  "collected_at": $(printf '%s' "$collected_at" | json_string),
  "hostname": $(printf '%s' "$host_name" | json_string),
  "os": {
    "name": $(printf '%s' "$os_name" | json_string),
    "version": $(printf '%s' "$os_version" | json_string),
    "kernel": $(printf '%s' "$kernel" | json_string)
  },
  "hardware": {
    "architecture": $(printf '%s' "$architecture" | json_string),
    "cpu_model": $(printf '%s' "$cpu_model" | json_string),
    "memory_total_mb": $(safe_number "$memory_total_mb"),
    "virtualization": $(printf '%s' "$virtualization" | json_string)
  },
  "uptime_seconds": $(safe_number "$uptime_seconds"),
  "resources": {
    "load_1m": $(safe_number "$load_1m"),
    "cpu_count": $(safe_number "$cpu_count"),
    "memory_used_percent": $(safe_number "$memory_used_percent"),
    "swap_used_percent": $(safe_number "$swap_used_percent")
  },
  "disk": [$disk_json],
  "updates": {
    "pending_total": $(safe_number "$pending_total"),
    "pending_security": $(safe_number "$pending_security"),
    "reboot_required": $(json_bool "$reboot_required")
  },
  "services": [$services_json],
  "docker": {
    "installed": $(json_bool "$docker_installed"),
    "containers_total": $(safe_number "$containers_total"),
    "containers_running": $(safe_number "$containers_running"),
    "unhealthy": [$docker_unhealthy_json],
    "inventory_collected": $(json_bool "$docker_inventory_collected"),
    "containers": $docker_containers_json
  },
  "security": {
    "failed_ssh_logins_24h": $(safe_number "$failed_ssh_logins_24h"),
    "successful_ssh_logins_24h": $(safe_number "$successful_ssh_logins_24h"),
    "last_login_summary": [$last_login_summary]
  },
  "issues": []
}
JSON
