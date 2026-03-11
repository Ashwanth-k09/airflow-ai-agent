#!/usr/bin/env python3
import subprocess, sys, time, json, os, re, getpass
from datetime import datetime

def silent_install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

for pkg in ["requests", "groq"]:
    try:
        __import__(pkg)
    except ImportError:
        print(f"Installing {pkg}...")
        silent_install(pkg)

try:
    from groq import Groq
except ImportError:
    silent_install("groq")
    from groq import Groq

from rule_engine import match_rule, get_all_rules_summary

R="\033[0m"; BOLD="\033[1m"; RED="\033[91m"; GREEN="\033[92m"
YELLOW="\033[93m"; BLUE="\033[94m"; MAGENTA="\033[95m"; CYAN="\033[96m"
WHITE="\033[97m"; GRAY="\033[90m"

def col(text, color, bold=False):
    return f"{BOLD if bold else ''}{color}{text}{R}"

def ts():
    return col(f"[{datetime.now().strftime('%H:%M:%S')}]", GRAY)

def log_info(msg):   print(f"{ts()} {col('INFO   ', BLUE, True)} {msg}")
def log_ok(msg):     print(f"{ts()} {col('SUCCESS', GREEN, True)} {col(msg, GREEN)}")
def log_err(msg):    print(f"{ts()} {col('ERROR  ', RED, True)} {col(msg, RED)}")
def log_warn(msg):   print(f"{ts()} {col('WARN   ', YELLOW, True)} {col(msg, YELLOW)}")
def log_rule(msg):   print(f"{ts()} {col('RULE   ', CYAN, True)} {col(msg, CYAN)}")
def log_ai(msg):     print(f"{ts()} {col('GROQ AI', MAGENTA, True)} {col(msg, MAGENTA)}")
def log_cmd(cmd):    print(f"           {col('$', GRAY)} {col(cmd, GRAY)}")

def divider(c="─", color=BLUE): print(col(c*60, color))

def banner():
    print(col("""
╔════════════════════════════════════════════════════════════╗
║      🚀  AIRFLOW AI INSTALLER AGENT (Groq + Rules)       ║
║  Installs Airflow • Auto-fixes errors • Continues steps  ║
╚════════════════════════════════════════════════════════════╝""", CYAN, True))

def section(title):
    print(f"\n{col('═'*60, BLUE)}\n{col('  '+title, YELLOW, True)}\n{col('═'*60, BLUE)}")

def log_step(n, name, total):
    print(f"\n{col('─'*60, BLUE)}")
    print(f"{ts()} {col(f'STEP {n}/{total}', BLUE, True)} {col(name, WHITE, True)}")
    print(col('─'*60, BLUE))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def ai_analyse_error(error_text, step_name, port, username, rule_match=None):
    if not GROQ_API_KEY:
        return None
    rule_ctx = ""
    if rule_match:
        rule_ctx = f"\nRule Engine matched: '{rule_match['id']}' — {rule_match['desc']}"
    prompt = f"""You are an expert Apache Airflow DevOps engineer.
Error at step: {step_name} | Port: {port} | User: {username}
ERROR: {error_text}
{rule_ctx}
Respond ONLY with valid JSON (no markdown):
{{"analysis":"1-2 sentence explanation","root_cause":"exact cause","solution":"plain English steps","commands":["shell","commands"],"severity":"low|medium|high|critical","can_auto_fix":true,"estimated_fix_time":"30 seconds"}}"""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        return {"analysis": str(e), "commands": [], "can_auto_fix": False, "severity": "unknown"}

def run_cmd_live(cmd, env_vars=None):
    merged = os.environ.copy()
    if env_vars: merged.update(env_vars)
    log_cmd(cmd)
    lines = []
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=merged)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(f"           {col('|', GRAY)} {line}")
                lines.append(line)
        proc.wait()
        return proc.returncode == 0, "\n".join(lines)
    except Exception as e:
        return False, str(e)

def handle_error(error_text, step_name, port, username, password):
    divider("─", RED)
    log_err(f"Error in: {step_name}")
    for line in error_text.split("\n")[:5]:
        if line.strip(): print(f"  {col(line, RED)}")
    divider("─", RED)
    env = {"AIRFLOW_HOME": os.path.expanduser("~/airflow")}

    print(f"\n{col('  [1/2] Rule Engine checking...', CYAN, True)}")
    rule = match_rule(error_text, port, username, password)
    rule_fixed = False
    if rule:
        log_rule(f"Matched : [{rule['id']}] {rule['desc']}")
        log_rule(f"Cause   : {rule['cause']}")
        log_rule(f"Severity: {rule['severity'].upper()}")
        print(f"\n{col('  Applying rule fix commands:', CYAN)}")
        for fix in rule["fixes"]:
            if fix.startswith("#"): print(f"  {col(fix, GRAY)}"); continue
            run_cmd_live(fix, env)
        log_ok("Rule Engine fix applied!")
        rule_fixed = True
    else:
        log_warn("No rule matched.")

    print(f"\n{col('  [2/2] Groq AI analysis...', MAGENTA, True)}")
    if not GROQ_API_KEY:
        log_warn("No GROQ_API_KEY — skipping AI.")
        return rule_fixed

    ai = ai_analyse_error(error_text, step_name, port, username, rule)
    if ai:
        divider("─", MAGENTA)
        print(col("  GROQ AI RESULT", MAGENTA, True))
        divider("─", MAGENTA)
        sev_col = RED if ai.get("severity") == "critical" else YELLOW
        print(f"  {col('Analysis  :', WHITE, True)} {ai.get('analysis','')}")
        print(f"  {col('Root Cause:', WHITE, True)} {ai.get('root_cause','')}")
        print(f"  {col('Solution  :', WHITE, True)} {ai.get('solution','')}")
        print(f"  {col('Severity  :', WHITE, True)} {col(ai.get('severity','?').upper(), sev_col)}")
        print(f"  {col('Auto-Fix  :', WHITE, True)} {col('YES', GREEN) if ai.get('can_auto_fix') else col('Manual needed', YELLOW)}")
        divider("─", MAGENTA)
        if not rule_fixed and ai.get("can_auto_fix") and ai.get("commands"):
            print(f"\n{col('  Applying AI fix commands:', GREEN)}")
            for cmd in ai["commands"]:
                if cmd.startswith("#"): print(f"  {col(cmd, GRAY)}"); continue
                cmd = cmd.replace("{PORT}", str(port)).replace("{USERNAME}", username).replace("{PASSWORD}", password)
                run_cmd_live(cmd, env)
            log_ok("Groq AI fix applied!")
            return True
        elif not rule_fixed:
            log_warn("Manual fix needed. Run these commands:")
            for cmd in ai.get("commands", []): print(f"  {col('$', GRAY)} {cmd}")
            return False
    return rule_fixed

def get_steps(port, username, password):
    ah = os.path.expanduser("~/airflow")
    return [
        {"id":1, "name":"Check Python & System",         "critical":True,  "timeout":60,  "env":{},                   "cmds":["python3 --version","df -h | head -3","free -h"]},
        {"id":2, "name":"Install System Dependencies",    "critical":True,  "timeout":180, "env":{},                   "cmds":["sudo apt-get update -y","sudo apt-get install -y python3-pip python3-venv build-essential libssl-dev libffi-dev python3-dev curl git"]},
        {"id":3, "name":"Upgrade pip setuptools wheel",   "critical":False, "timeout":120, "env":{},                   "cmds":["pip3 install --upgrade pip setuptools wheel"]},
        {"id":4, "name":"Create Airflow Home Directory",  "critical":True,  "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":[f"mkdir -p {ah}/dags {ah}/logs {ah}/plugins",f"chmod -R 755 {ah}","echo 'Airflow home ready'"]},
        {"id":5, "name":"Install Apache Airflow 2.8.0",   "critical":True,  "timeout":600, "env":{"AIRFLOW_HOME":ah},  "cmds":['pip install "apache-airflow==2.8.0" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.0/constraints-3.8.txt"']},
        {"id":6, "name":"Verify Airflow Installation",    "critical":True,  "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":["airflow version"]},
        {"id":7, "name":"Initialize Airflow Database",    "critical":True,  "timeout":120, "env":{"AIRFLOW_HOME":ah},  "cmds":["airflow db init"]},
        {"id":8, "name":f"Check Port {port} Available",   "critical":False, "timeout":30,  "env":{},                   "cmds":[f"fuser {port}/tcp 2>/dev/null && echo 'WARNING: Port {port} in use!' || echo 'Port {port} is FREE'"]},
        {"id":9, "name":"Create Admin User",              "critical":True,  "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":[f"airflow users create --username {username} --firstname Admin --lastname User --role Admin --email admin@airflow.com --password {password}"]},
        {"id":10,"name":f"Start Webserver on Port {port}","critical":True,  "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":[f"airflow webserver --port {port} --daemon"]},
        {"id":11,"name":"Start Scheduler",                "critical":False, "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":["airflow scheduler --daemon"]},
        {"id":12,"name":"Wait for Airflow to Boot",       "critical":False, "timeout":20,  "env":{},                   "cmds":["echo 'Waiting 15s...'","sleep 15"]},
        {"id":13,"name":"Health Check",                   "critical":False, "timeout":30,  "env":{"AIRFLOW_HOME":ah},  "cmds":[f"curl -s http://localhost:{port}/health || echo 'Still booting...'"]},
    ]

def get_user_inputs():
    section("CONFIGURATION — Enter Your Details")
    while True:
        port = input(col("  Port for Airflow UI [default 8080]: ", CYAN)).strip() or "8080"
        if port.isdigit() and 1024 <= int(port) <= 65535: break
        print(col("  Enter valid port 1024-65535", YELLOW))
    while True:
        username = input(col("  Admin Username [default admin]: ", CYAN)).strip() or "admin"
        if len(username) >= 3: break
        print(col("  Username must be 3+ chars", YELLOW))
    while True:
        password = getpass.getpass(col("  Admin Password (hidden): ", CYAN))
        if len(password) >= 6: break
        print(col("  Password must be 6+ chars", YELLOW))
    print(f"\n  {col('Port    :', GRAY)} {col(port, GREEN)}")
    print(f"  {col('Username:', GRAY)} {col(username, GREEN)}")
    print(f"  {col('URL     :', GRAY)} {col(f'http://localhost:{port}', BLUE)}")
    go = input(col("\n  Press ENTER to start (or n to cancel): ", YELLOW)).strip().lower()
    if go == "n": print(col("Cancelled.", RED)); sys.exit(0)
    return port, username, password

def run_installer(port, username, password):
    steps = get_steps(port, username, password)
    total = len(steps)
    base_env = {"AIRFLOW_HOME": os.path.expanduser("~/airflow")}
    failed, skipped = [], []
    section(f"INSTALLATION STARTED — {total} Steps")
    for step in steps:
        sid, sname = step["id"], step["name"]
        env = {**base_env, **step.get("env", {})}
        log_step(sid, sname, total)
        step_failed = False; error_out = ""
        for cmd in step["cmds"]:
            ok, out = run_cmd_live(cmd, env)
            if not ok: step_failed = True; error_out = out; break
        if not step_failed:
            log_ok(f"Step {sid} done: {sname}"); continue
        log_warn(f"Step {sid} failed — activating Rule Engine + Groq AI...")
        fixed = handle_error(error_out, sname, port, username, password)
        if fixed:
            log_info(f"Retrying Step {sid}...")
            retry_ok = True
            for cmd in step["cmds"]:
                ok, out = run_cmd_live(cmd, env)
                if not ok: retry_ok = False; break
            if retry_ok: log_ok(f"Step {sid} completed after fix!")
            else:
                log_err(f"Step {sid} still failing after fix.")
                failed.append(sid)
                if step.get("critical"): log_err("Critical step failed. Stopping."); break
        else:
            if step.get("critical"): log_err(f"Critical Step {sid} unfixable. Stopping."); failed.append(sid); break
            else: log_warn(f"Skipping non-critical Step {sid}."); skipped.append(sid)
    return failed, skipped

def print_report(port, username, failed, skipped):
    section("INSTALLATION REPORT")
    if not failed:
        print(col("""
  ╔══════════════════════════════════════════════════════╗
  ║        🎉  AIRFLOW IS READY!                        ║
  ╚══════════════════════════════════════════════════════╝""", GREEN, True))
        print(f"\n  {col('Airflow UI :', WHITE, True)} {col(f'http://localhost:{port}', BLUE, True)}")
        print(f"  {col('Username   :', WHITE, True)} {col(username, GREEN)}")
        print(f"  {col('Airflow Dir:', WHITE, True)} {col('~/airflow', CYAN)}")
        print(f"\n  {col('Useful Commands:', WHITE, True)}")
        print(f"  {col('List DAGs  :', GRAY)} airflow dags list")
        print(f"  {col('Stop all   :', GRAY)} pkill -f airflow")
        print(f"  {col('View logs  :', GRAY)} tail -f ~/airflow/logs/scheduler/latest/*.log")
    else:
        print(col(f"\n  Installation had issues. Failed steps: {failed}", YELLOW))
        print(col("  Fix the errors above and re-run: python3 airflow_agent.py", GRAY))
    if skipped: print(f"\n  {col('Skipped (non-critical):', GRAY)} {skipped}")
    print(); divider("═")

def main():
    banner()
    global GROQ_API_KEY
    if not GROQ_API_KEY:
        print(col("\n  Groq API key not found in environment.", YELLOW))
        key = input(col("  Enter your Groq API key (or Enter to use Rule Engine only): ", CYAN)).strip()
        if key: GROQ_API_KEY = key; os.environ["GROQ_API_KEY"] = key
        else: log_warn("Proceeding with Rule Engine only.")
    rules_count = len(get_all_rules_summary())
    print(f"\n  {col('Rule Engine:', WHITE, True)} {col(f'{rules_count} rules loaded', GREEN)}")
    print(f"  {col('Groq AI    :', WHITE, True)} {col('Connected' if GROQ_API_KEY else 'Disabled', GREEN if GROQ_API_KEY else YELLOW)}")
    port, username, password = get_user_inputs()
    start = time.time()
    failed, skipped = run_installer(port, username, password)
    elapsed = round(time.time() - start, 1)
    print_report(port, username, failed, skipped)
    print(col(f"  Total time: {elapsed}s\n", GRAY))

if __name__ == "__main__":
    main()
