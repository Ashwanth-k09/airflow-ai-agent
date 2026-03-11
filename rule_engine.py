import re

RULES = [
    {
        "id": "python_not_found",
        "patterns": [r"python.*not found", r"command not found.*python"],
        "desc": "Python is not installed",
        "cause": "Python3 missing from system",
        "fixes": ["sudo apt-get update -y", "sudo apt-get install -y python3 python3-pip", "sudo ln -sf /usr/bin/python3 /usr/bin/python"],
        "severity": "critical"
    },
    {
        "id": "pip_not_found",
        "patterns": [r"pip.*not found", r"command not found.*pip"],
        "desc": "pip is not installed",
        "cause": "pip package manager missing",
        "fixes": ["sudo apt-get install -y python3-pip", "python3 -m ensurepip --upgrade"],
        "severity": "high"
    },
    {
        "id": "python_version_old",
        "patterns": [r"python 3\.[0-7]\.", r"requires python.*3\.[89]"],
        "desc": "Python version too old (need 3.8+)",
        "cause": "Airflow 2.x requires Python 3.8+",
        "fixes": ["sudo apt-get install -y python3.8", "sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1"],
        "severity": "critical"
    },
    {
        "id": "disk_full",
        "patterns": [r"no space left on device", r"disk.*full", r"ENOSPC"],
        "desc": "Disk is full",
        "cause": "No disk space for installation",
        "fixes": ["df -h", "sudo apt-get clean", "sudo apt-get autoremove -y", "sudo rm -rf /tmp/*"],
        "severity": "critical"
    },
    {
        "id": "memory_error",
        "patterns": [r"out of memory", r"MemoryError", r"cannot allocate memory"],
        "desc": "System out of memory",
        "cause": "Not enough RAM",
        "fixes": ["free -h", "sudo fallocate -l 2G /swapfile", "sudo chmod 600 /swapfile", "sudo mkswap /swapfile", "sudo swapon /swapfile"],
        "severity": "critical"
    },
    {
        "id": "permission_denied",
        "patterns": [r"permission denied", r"EACCES", r"access.*denied"],
        "desc": "Permission denied",
        "cause": "Insufficient privileges",
        "fixes": ["sudo chmod -R 755 ~/airflow", "sudo chown -R $USER:$USER ~/airflow"],
        "severity": "high"
    },
    {
        "id": "port_in_use",
        "patterns": [r"address already in use", r"port.*in use", r"EADDRINUSE"],
        "desc": "Port already occupied",
        "cause": "Another process using the port",
        "fixes": ["sudo fuser -k {PORT}/tcp", "sleep 2"],
        "severity": "high"
    },
    {
        "id": "network_timeout",
        "patterns": [r"timed? ?out", r"ETIMEDOUT", r"connection.*timed out"],
        "desc": "Network timeout",
        "cause": "Slow or unstable internet",
        "fixes": ["ping -c 3 pypi.org", "pip install apache-airflow --timeout 120 --retries 5"],
        "severity": "medium"
    },
    {
        "id": "connection_refused",
        "patterns": [r"connection refused", r"ECONNREFUSED"],
        "desc": "Connection refused",
        "cause": "Server unreachable or firewall blocking",
        "fixes": ["ping -c 3 8.8.8.8", "curl -I https://pypi.org"],
        "severity": "high"
    },
    {
        "id": "dns_failure",
        "patterns": [r"name.*resolution.*failed", r"could not resolve host"],
        "desc": "DNS resolution failed",
        "cause": "Cannot resolve hostnames",
        "fixes": ["echo 'nameserver 8.8.8.8' | sudo tee /etc/resolv.conf", "echo 'nameserver 1.1.1.1' | sudo tee -a /etc/resolv.conf"],
        "severity": "high"
    },
    {
        "id": "ssl_error",
        "patterns": [r"ssl.*error", r"certificate.*verify.*failed", r"SSLError"],
        "desc": "SSL certificate error",
        "cause": "SSL/TLS issue or expired certificates",
        "fixes": ["sudo apt-get install -y ca-certificates", "sudo update-ca-certificates", "pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org apache-airflow"],
        "severity": "high"
    },
    {
        "id": "dependency_conflict",
        "patterns": [r"conflict", r"incompatible.*version", r"ResolutionImpossible"],
        "desc": "Package dependency conflict",
        "cause": "Conflicting package versions",
        "fixes": ["pip install --upgrade pip setuptools wheel", "pip install apache-airflow --upgrade --ignore-installed"],
        "severity": "high"
    },
    {
        "id": "package_not_found",
        "patterns": [r"no.*module.*named", r"ModuleNotFoundError", r"ImportError"],
        "desc": "Python module not found",
        "cause": "Missing dependency",
        "fixes": ["pip install --upgrade apache-airflow"],
        "severity": "high"
    },
    {
        "id": "wheel_build_failed",
        "patterns": [r"failed.*build.*wheel", r"error.*building wheel"],
        "desc": "Wheel build failed",
        "cause": "Missing system build tools",
        "fixes": ["sudo apt-get install -y build-essential python3-dev libssl-dev libffi-dev", "pip install --upgrade pip wheel setuptools"],
        "severity": "high"
    },
    {
        "id": "db_init_failed",
        "patterns": [r"database.*init.*fail", r"db.*error", r"sqlite.*error"],
        "desc": "Airflow database init failed",
        "cause": "Corrupt or missing DB file",
        "fixes": ["rm -f ~/airflow/airflow.db", "export AIRFLOW_HOME=~/airflow", "airflow db init"],
        "severity": "high"
    },
    {
        "id": "db_locked",
        "patterns": [r"database.*locked", r"sqlite.*locked"],
        "desc": "Database is locked",
        "cause": "Another process using the DB",
        "fixes": ["pkill -f airflow", "sleep 3", "airflow db check"],
        "severity": "medium"
    },
    {
        "id": "db_migration_failed",
        "patterns": [r"migration.*fail", r"alembic.*head", r"db.*upgrade.*fail"],
        "desc": "Database migration failed",
        "cause": "Airflow version DB schema mismatch",
        "fixes": ["export AIRFLOW_HOME=~/airflow", "airflow db reset --yes", "airflow db init"],
        "severity": "high"
    },
    {
        "id": "airflow_home_missing",
        "patterns": [r"AIRFLOW_HOME.*not set", r"no.*airflow.*config"],
        "desc": "AIRFLOW_HOME not set",
        "cause": "Airflow home directory not configured",
        "fixes": ["export AIRFLOW_HOME=~/airflow", "mkdir -p ~/airflow/dags ~/airflow/logs ~/airflow/plugins", "echo 'export AIRFLOW_HOME=~/airflow' >> ~/.bashrc"],
        "severity": "high"
    },
    {
        "id": "webserver_failed",
        "patterns": [r"webserver.*failed", r"gunicorn.*error", r"worker.*failed.*boot"],
        "desc": "Airflow webserver failed to start",
        "cause": "Webserver process crashed",
        "fixes": ["pkill -f 'airflow webserver'", "rm -f ~/airflow/airflow-webserver.pid", "sleep 2", "airflow webserver --port {PORT} -D"],
        "severity": "high"
    },
    {
        "id": "scheduler_failed",
        "patterns": [r"scheduler.*failed", r"scheduler.*error"],
        "desc": "Airflow scheduler failed",
        "cause": "Scheduler process crashed",
        "fixes": ["pkill -f 'airflow scheduler'", "rm -f ~/airflow/airflow-scheduler.pid", "airflow scheduler -D"],
        "severity": "high"
    },
    {
        "id": "user_already_exists",
        "patterns": [r"user.*already.*exists", r"duplicate.*user"],
        "desc": "Admin user already exists",
        "cause": "User created in a previous run",
        "fixes": ["airflow users delete --username {USERNAME} 2>/dev/null || true", "airflow users create --username {USERNAME} --firstname Admin --lastname User --role Admin --email admin@airflow.com --password {PASSWORD}"],
        "severity": "low"
    },
    {
        "id": "fernet_key_error",
        "patterns": [r"fernet.*key", r"invalid.*fernet"],
        "desc": "Fernet encryption key error",
        "cause": "Missing or invalid Fernet key",
        "fixes": ["python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""],
        "severity": "high"
    },
    {
        "id": "libpq_missing",
        "patterns": [r"libpq.*not found", r"pg_config.*not found"],
        "desc": "PostgreSQL client library missing",
        "cause": "libpq-dev not installed",
        "fixes": ["sudo apt-get install -y libpq-dev postgresql-client", "pip install psycopg2-binary"],
        "severity": "medium"
    },
    {
        "id": "libssl_missing",
        "patterns": [r"libssl.*not found", r"openssl.*error"],
        "desc": "OpenSSL library missing",
        "cause": "libssl-dev not installed",
        "fixes": ["sudo apt-get install -y libssl-dev openssl", "pip install cryptography --upgrade"],
        "severity": "high"
    },
    {
        "id": "pip_upgrade_needed",
        "patterns": [r"upgrade pip", r"consider upgrading pip"],
        "desc": "pip needs upgrading",
        "cause": "Outdated pip version",
        "fixes": ["python3 -m pip install --upgrade pip"],
        "severity": "low"
    },
    {
        "id": "git_not_found",
        "patterns": [r"git.*not found", r"command not found.*git"],
        "desc": "Git not installed",
        "cause": "Git binary missing",
        "fixes": ["sudo apt-get install -y git", "git --version"],
        "severity": "medium"
    },
    {
        "id": "virtualenv_error",
        "patterns": [r"virtualenv.*error", r"venv.*failed"],
        "desc": "Virtual environment error",
        "cause": "venv module missing or broken",
        "fixes": ["sudo apt-get install -y python3-venv", "python3 -m venv ~/airflow_venv", "source ~/airflow_venv/bin/activate"],
        "severity": "medium"
    },
    {
        "id": "health_check_failed",
        "patterns": [r"health.*check.*failed", r"curl.*failed", r"connection.*refused.*localhost"],
        "desc": "Airflow health check failed",
        "cause": "Webserver not ready or crashed",
        "fixes": ["sleep 10", "curl -s http://localhost:{PORT}/health"],
        "severity": "medium"
    },
    {
        "id": "constraint_error",
        "patterns": [r"constraint.*fail", r"version.*constraint"],
        "desc": "Airflow version constraint conflict",
        "cause": "Constraint file version mismatch",
        "fixes": ["pip install apache-airflow==2.8.0 --no-deps", "pip install apache-airflow==2.8.0 --ignore-installed"],
        "severity": "high"
    },
    {
        "id": "proxy_error",
        "patterns": [r"proxy.*error", r"407.*proxy"],
        "desc": "Proxy configuration error",
        "cause": "HTTP proxy blocking",
        "fixes": ["unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY", "pip install apache-airflow --no-cache-dir"],
        "severity": "medium"
    },
]

def match_rule(error_text, port="8080", username="admin", password="admin"):
    error_lower = error_text.lower()
    for rule in RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, error_lower, re.IGNORECASE):
                fixed_rule = dict(rule)
                fixed_rule["fixes"] = [
                    f.replace("{PORT}", str(port)).replace("{USERNAME}", username).replace("{PASSWORD}", password)
                    for f in rule["fixes"]
                ]
                return fixed_rule
    return None

def get_all_rules_summary():
    return [(r["id"], r["desc"], r["severity"]) for r in RULES]
