import subprocess, sys, os, shutil, platform, re

R="\033[0m"; BOLD="\033[1m"; RED="\033[91m"; GREEN="\033[92m"
YELLOW="\033[93m"; BLUE="\033[94m"; CYAN="\033[96m"; WHITE="\033[97m"; GRAY="\033[90m"

def col(t, c, b=False): return f"{BOLD if b else ''}{c}{t}{R}"
def ok(m):   print(f"  {col('CHECK PASS', GREEN, True)} {col(m, GREEN)}")
def fail(m): print(f"  {col('CHECK FAIL', RED, True)} {col(m, RED)}")
def info(m): print(f"  {col('INSTALLING', CYAN, True)} {col(m, CYAN)}")
def warn(m): print(f"  {col('WARNING   ', YELLOW, True)} {col(m, YELLOW)}")

def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except: return False, "failed"

def run_live(cmd, timeout=300):
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            line = line.rstrip()
            if line: print(f"     {col('|', GRAY)} {line}")
        proc.wait(timeout=timeout)
        return proc.returncode == 0
    except Exception as e:
        print(f"     {col('Error:', RED)} {e}"); return False

def check_os():
    print(col("\n  [CHECK 1] Operating System", WHITE, True))
    if platform.system() == "Linux":
        _, d = run("lsb_release -d 2>/dev/null || cat /etc/os-release | head -1")
        ok(f"Linux: {d[:50]}"); return True
    fail("Airflow requires Linux."); return False

def check_internet():
    print(col("\n  [CHECK 2] Internet Connectivity", WHITE, True))
    for h in ["8.8.8.8", "pypi.org"]:
        s, _ = run(f"ping -c 1 -W 3 {h} 2>/dev/null")
        if s: ok(f"Internet OK (reached {h})"); return True
    fail("No internet connection."); return False

def check_disk_space():
    print(col("\n  [CHECK 3] Disk Space (5GB required)", WHITE, True))
    try:
        st = os.statvfs(os.path.expanduser("~"))
        gb = (st.f_bavail * st.f_frsize) / (1024**3)
        if gb >= 5: ok(f"Disk OK — {gb:.1f}GB free"); return True
        fail(f"Only {gb:.1f}GB free. Trying to free space...")
        run_live("sudo apt-get clean -y && sudo apt-get autoremove -y && sudo rm -rf /tmp/*")
        st2 = os.statvfs(os.path.expanduser("~"))
        gb2 = (st2.f_bavail * st2.f_frsize) / (1024**3)
        if gb2 >= 5: ok(f"Freed space — {gb2:.1f}GB now free"); return True
        fail(f"Still only {gb2:.1f}GB. Manual cleanup needed."); return False
    except: warn("Could not check disk."); return True

def check_ram():
    print(col("\n  [CHECK 4] RAM (1GB required)", WHITE, True))
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemAvailable" in line:
                    mb = int(line.split()[1]) // 1024
                    if mb >= 1024: ok(f"RAM OK — {mb}MB available"); return True
                    info(f"Only {mb}MB RAM — adding swap space...")
                    for c in ["sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048",
                              "sudo chmod 600 /swapfile", "sudo mkswap /swapfile", "sudo swapon /swapfile"]:
                        run_live(c)
                    ok("Swap space added (2GB)"); return True
    except: pass
    warn("Could not check RAM — proceeding."); return True

def check_python():
    print(col("\n  [CHECK 5] Python 3.8+", WHITE, True))
    s, v = run("python3 --version 2>&1")
    if s and "Python 3" in v:
        try:
            parts = v.split()[1].split(".")
            if int(parts[0]) == 3 and int(parts[1]) >= 8:
                ok(f"Python OK: {v.strip()}"); return True
        except: pass
    info("Python 3.8+ not found — installing...")
    run_live("sudo apt-get update -y")
    run_live("sudo apt-get install -y python3.8 python3.8-dev python3.8-venv")
    run_live("sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1")
    run_live("sudo ln -sf /usr/bin/python3 /usr/bin/python 2>/dev/null || true")
    s2, v2 = run("python3 --version 2>&1")
    if s2: ok(f"Python installed: {v2.strip()}"); return True
    fail("Could not install Python 3.8+"); return False

def check_pip():
    print(col("\n  [CHECK 6] pip", WHITE, True))
    s, v = run("pip3 --version 2>&1")
    if s: ok(f"pip found: {v[:50]}"); run_live("python3 -m pip install --upgrade pip -q"); return True
    info("pip not found — installing...")
    run_live("sudo apt-get install -y python3-pip")
    run_live("python3 -m ensurepip --upgrade")
    s2, v2 = run("pip3 --version 2>&1")
    if s2: ok(f"pip installed: {v2[:50]}"); return True
    fail("Could not install pip"); return False

def check_setuptools():
    print(col("\n  [CHECK 7] setuptools & wheel", WHITE, True))
    run_live("pip3 install --upgrade setuptools wheel -q")
    ok("setuptools and wheel ready"); return True

def check_venv():
    print(col("\n  [CHECK 8] python3-venv", WHITE, True))
    s, _ = run("python3 -m venv --help 2>&1")
    if s: ok("python3-venv available"); return True
    run_live("sudo apt-get install -y python3-venv python3-dev")
    ok("python3-venv installed"); return True

def check_build_tools():
    print(col("\n  [CHECK 9] Build Tools (gcc, make)", WHITE, True))
    missing = [t for t in ["gcc", "make"] if not shutil.which(t)]
    if not missing: ok("Build tools already installed"); return True
    info(f"Installing build-essential (missing: {missing})...")
    run_live("sudo apt-get install -y build-essential gcc g++ make")
    ok("Build tools installed"); return True

def check_system_libs():
    print(col("\n  [CHECK 10] System Libraries (libssl, libffi, python3-dev)", WHITE, True))
    _, installed = run("dpkg -l 2>/dev/null | awk '{print $2}'")
    installed_set = set(installed.split("\n"))
    to_install = [p for p in ["libssl-dev", "libffi-dev", "python3-dev"] if not any(p in x for x in installed_set)]
    if not to_install: ok("All system libraries present"); return True
    info(f"Installing: {to_install}")
    run_live(f"sudo apt-get install -y {' '.join(to_install)}")
    ok("System libraries installed"); return True

def check_curl():
    print(col("\n  [CHECK 11] curl", WHITE, True))
    if shutil.which("curl"): ok("curl installed"); return True
    run_live("sudo apt-get install -y curl")
    ok("curl installed"); return True

def check_git():
    print(col("\n  [CHECK 12] git", WHITE, True))
    if shutil.which("git"): _, v = run("git --version"); ok(f"git: {v}"); return True
    run_live("sudo apt-get install -y git")
    ok("git installed"); return True

def check_groq_package():
    print(col("\n  [CHECK 13] groq Python package", WHITE, True))
    try: import groq; ok("groq package ready"); return True
    except ImportError:
        run_live("pip3 install groq -q")
        try: import groq; ok("groq installed"); return True
        except: fail("groq install failed"); return False

def check_requests_package():
    print(col("\n  [CHECK 14] requests Python package", WHITE, True))
    try: import requests; ok("requests ready"); return True
    except ImportError:
        run_live("pip3 install requests -q")
        ok("requests installed"); return True

def check_env_variables():
    print(col("\n  [CHECK 15] AIRFLOW_HOME environment variable", WHITE, True))
    ah = os.path.expanduser("~/airflow")
    if not os.environ.get("AIRFLOW_HOME"):
        os.environ["AIRFLOW_HOME"] = ah
        with open(os.path.expanduser("~/.bashrc"), "a") as f:
            f.write(f'\nexport AIRFLOW_HOME={ah}\n')
        info(f"AIRFLOW_HOME={ah} set and saved to ~/.bashrc")
    ok(f"AIRFLOW_HOME={os.environ['AIRFLOW_HOME']}"); return True

def check_airflow_dirs():
    print(col("\n  [CHECK 16] Airflow Directories", WHITE, True))
    ah = os.path.expanduser("~/airflow")
    for d in [ah, f"{ah}/dags", f"{ah}/logs", f"{ah}/plugins"]:
        os.makedirs(d, exist_ok=True)
    ok(f"Airflow directories ready at {ah}"); return True

def check_port_tools():
    print(col("\n  [CHECK 17] Port tools (lsof, fuser)", WHITE, True))
    if all(shutil.which(t) for t in ["lsof", "fuser"]): ok("Port tools available"); return True
    run_live("sudo apt-get install -y lsof psmisc")
    ok("Port tools installed"); return True

def check_sudo():
    print(col("\n  [CHECK 18] sudo access", WHITE, True))
    if shutil.which("sudo"): ok("sudo available"); return True
    warn("sudo not found — some steps may fail"); return True

def run_all_checks():
    print(col("""
╔══════════════════════════════════════════════════════════════╗
║    PHASE 1 - PREREQUISITES CHECK (18 checks)                ║
║    Auto-installing anything that is missing...              ║
╚══════════════════════════════════════════════════════════════╝""", CYAN, True))

    run_live("sudo apt-get update -y -q 2>/dev/null")

    checks = [
        ("Operating System",          check_os,              True),
        ("Internet Connectivity",     check_internet,        True),
        ("Disk Space 5GB",            check_disk_space,      True),
        ("RAM 1GB",                   check_ram,             False),
        ("Python 3.8+",              check_python,          True),
        ("pip",                       check_pip,             True),
        ("setuptools & wheel",        check_setuptools,      False),
        ("python3-venv",              check_venv,            False),
        ("Build Tools",               check_build_tools,     False),
        ("System Libraries",          check_system_libs,     False),
        ("curl",                      check_curl,            False),
        ("git",                       check_git,             False),
        ("groq package",              check_groq_package,    True),
        ("requests package",          check_requests_package,True),
        ("AIRFLOW_HOME variable",     check_env_variables,   False),
        ("Airflow Directories",       check_airflow_dirs,    True),
        ("Port Tools",                check_port_tools,      False),
        ("sudo access",               check_sudo,            False),
    ]

    results = []
    for name, fn, is_critical in checks:
        try: passed = fn()
        except Exception as e: warn(f"Check '{name}' error: {e}"); passed = False
        results.append((name, passed, is_critical))

    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    critical_failed = any(not p and c for _, p, c in results)

    print(col("\n══════════════════════════════════════════════════════════════", BLUE))
    print(col("  PREREQUISITES SUMMARY", YELLOW, True))
    print(col("══════════════════════════════════════════════════════════════", BLUE))
    for name, passed, is_critical in results:
        tag = col("CRITICAL", RED) if is_critical else col("optional", GRAY)
        icon = col("PASS", GREEN, True) if passed else col("FAIL", RED, True)
        print(f"  [{icon}] {col(name, GREEN if passed else RED):<38} [{tag}]")

    pct = int((passed_count / total) * 100)
    c_result = GREEN if not critical_failed else RED
    print(col("──────────────────────────────────────────────────────────────", BLUE))
    print(f"  {col(f'Result: {passed_count}/{total} checks passed ({pct}%)', c_result, True)}")

    if critical_failed:
        print(col("\n  CRITICAL checks failed. Fix above issues and re-run.", RED, True))
    else:
        print(col("\n  All critical checks passed! Proceeding to installation.", GREEN, True))
    print(col("══════════════════════════════════════════════════════════════\n", BLUE))
    return not critical_failed, results
