# Plugin Provisioning

This directory is intentionally empty of plugin definitions. HomeOps disables
Grafana's bundled-plugin preinstaller because the container filesystem is
read-only and plugins must be introduced through a reviewed image or bundle.
