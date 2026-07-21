# Local Monitoring Secrets

This directory exists so the approval-gated secret action can retain a local
recovery copy of the Grafana admin password. Every file here except this README
is ignored by Git.

Do not paste the password into documentation, action arguments, reports, or
chat. The expected ignored file is `grafana_admin_password`.
