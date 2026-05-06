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
      used=$5
      free=$4
      gsub("%", "", used)
      gsub("G", "", free)
      if (count > 0) {
        printf ","
      }
      printf "{\"mount\":\"%s\",\"used_percent\":%s,\"free_gb\":%s}", mount, used, free
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

service_names="${HOMEOPS_SERVICES:-ssh sshd docker openvpn openvpn-server@server openvpnas agent-dvr}"
services_json=""
for service in $service_names; do
  if systemctl list-unit-files "$service.service" >/dev/null 2>&1 || systemctl status "$service" >/dev/null 2>&1; then
    state="$(systemctl is-active "$service" 2>/dev/null || printf 'unknown')"
    enabled_raw="$(systemctl is-enabled "$service" 2>/dev/null || printf 'false')"
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
    "unhealthy": [$docker_unhealthy_json]
  },
  "security": {
    "failed_ssh_logins_24h": $(safe_number "$failed_ssh_logins_24h"),
    "successful_ssh_logins_24h": $(safe_number "$successful_ssh_logins_24h"),
    "last_login_summary": [$last_login_summary]
  },
  "issues": []
}
JSON
