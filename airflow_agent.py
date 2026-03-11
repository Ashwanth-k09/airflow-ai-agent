#!/usr/bin/env python3
import subprocess, sys, time, json, os, re, getpass
from datetime import datetime

def bootstrap():
    for pkg in ["requests","groq"]:
        try: __import__(pkg)
        except ImportError:
            print(f"  [bootstrap] Installing {pkg}...")
            subprocess.check_call([sys.executable,"-m","pip","install",pkg,"-q"])
bootstrap()

from groq import Groq
from rule_engine import match_rule, get_all_rules_summary
from prerequisites import run_all_checks

R="\033[0m"; BOLD="\033[1m"; RED="\033[91m"; GREEN="\033[92m"
YELLOW="\033[93m"; BLUE="\033[94m"; MAGENTA="\033[95m"
CYAN="\033[96m"; WHITE="\033[97m"; GRAY="\033[90m"

def col(t,c,b=False): return f"{BOLD if b else ''}{c}{t}{R}"
def ts(): return col(f"[{datetime.now().strftime('%H:%M:%S')}]",GRAY)
def log_ok(m):   print(f"{ts()} {col('SUCCESS',GREEN,True)}  {col(m,GREEN)}")
def log_err(m):  print(f"{ts()} {col('ERROR  ',RED,True)}  {col(m,RED)}")
def log_warn(m): print(f"{ts()} {col('WARN   ',YELLOW,True)}  {col(m,YELLOW)}")
def log_rule(m): print(f"{ts()} {col('RULE   ',CYAN,True)}  {col(m,CYAN)}")
def log_info(m): print(f"{ts()} {col('INFO   ',BLUE,True)}  {m}")
def log_cmd(c):  print(f"           {col('$',GRAY)} {col(c,GRAY)}")
def divider(c="─",color=BLUE): print(col(c*62,color))

def banner():
    print(col("""
╔══════════════════════════════════════════════════════════════╗
║          AIRFLOW AI INSTALLER AGENT                         ║
║  PHASE 1  Check and install all 18 prerequisites            ║
║  PHASE 2  Install Apache Airflow (10 steps)                 ║
║  PHASE 3  Rule Engine + Groq AI auto-fix on any error       ║
║  PHASE 4  Continue steps after fix and final report         ║
╚══════════════════════════════════════════════════════════════╝""",CYAN,True))

def section(t):
    print(f"\n{col('═'*62,BLUE)}\n{col('  '+t,YELLOW,True)}\n{col('═'*62,BLUE)}")

def log_step(n,name,total):
    print(f"\n{col('─'*62,BLUE)}")
    print(f"{ts()} {col(f'STEP {n}/{total}',BLUE,True)} {col(name,WHITE,True)}")
    print(col('─'*62,BLUE))

GROQ_API_KEY=os.environ.get("GROQ_API_KEY","")

def ai_analyse(err,step,port,user,rule=None):
    if not GROQ_API_KEY: return None
    ctx=f"\nRule matched: '{rule['id']}'" if rule else ""
    p=f"""Expert Airflow DevOps engineer. Error at: {step} | Port:{port} | User:{user}
ERROR: {err}{ctx}
Respond ONLY valid JSON:
{{"analysis":"brief","root_cause":"cause","solution":"steps","commands":["cmds"],"severity":"low|medium|high|critical","can_auto_fix":true,"estimated_fix_time":"30s"}}"""
    try:
        c=Groq(api_key=GROQ_API_KEY)
        r=c.chat.completions.create(model="llama3-70b-8192",messages=[{"role":"user","content":p}],temperature=0.1,max_tokens=800)
        raw=re.sub(r"```json|```","",r.choices[0].message.content.strip()).strip()
        return json.loads(raw)
    except Exception as e:
        return {"analysis":str(e),"commands":[],"can_auto_fix":False,"severity":"unknown"}

def run_live(cmd,env_vars=None):
    m=os.environ.copy()
    if env_vars: m.update(env_vars)
    log_cmd(cmd); lines=[]
    try:
        proc=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=m)
        for line in proc.stdout:
            line=line.rstrip()
            if line: print(f"           {col('|',GRAY)} {line}"); lines.append(line)
        proc.wait()
        return proc.returncode==0,"\n".join(lines)
    except Exception as e: return False,str(e)

def handle_error(err,step,port,username,password):
    divider("─",RED)
    log_err(f"Error in: {step}")
    for line in err.split("\n")[:5]:
        if line.strip(): print(f"  {col(line,RED)}")
    divider("─",RED)
    env={"AIRFLOW_HOME":os.path.expanduser("~/airflow")}
    print(f"\n{col('  [1/2] Rule Engine scanning...',CYAN,True)}")
    rule=match_rule(err,port,username,password)
    rule_fixed=False
    if rule:
        log_rule(f"Matched : [{rule['id']}] {rule['desc']}")
        log_rule(f"Cause   : {rule['cause']}")
        log_rule(f"Severity: {rule['severity'].upper()}")
        print(f"\n{col('  Applying Rule Engine fix:',CYAN)}")
        for fx in rule["fixes"]:
            if fx.startswith("#"): print(f"  {col(fx,GRAY)}"); continue
            run_live(fx,env)
        log_ok("Rule Engine fix applied!"); rule_fixed=True
    else: log_warn("No rule matched — escalating to Groq AI.")
    print(f"\n{col('  [2/2] Groq AI analysing...',MAGENTA,True)}")
    if not GROQ_API_KEY: log_warn("No GROQ_API_KEY."); return rule_fixed
    ai=ai_analyse(err,step,port,username,rule)
    if ai:
        divider("─",MAGENTA)
        print(col("  GROQ AI ANALYSIS",MAGENTA,True)); divider("─",MAGENTA)
        sc=RED if ai.get("severity")=="critical" else YELLOW
        print(f"  {col('Analysis  :',WHITE,True)} {ai.get('analysis','')}")
        print(f"  {col('Root Cause:',WHITE,True)} {ai.get('root_cause','')}")
        print(f"  {col('Solution  :',WHITE,True)} {ai.get('solution','')}")
        print(f"  {col('Severity  :',WHITE,True)} {col(ai.get('severity','?').upper(),sc)}")
        print(f"  {col('Auto-Fix  :',WHITE,True)} {col('YES',GREEN) if ai.get('can_auto_fix') else col('Manual needed',YELLOW)}")
        divider("─",MAGENTA)
        if not rule_fixed and ai.get("can_auto_fix") and ai.get("commands"):
            for cmd in ai["commands"]:
                if cmd.startswith("#"): continue
                cmd=cmd.replace("{PORT}",str(port)).replace("{USERNAME}",username).replace("{PASSWORD}",password)
                run_live(cmd,env)
            log_ok("Groq AI fix applied!"); return True
        elif not rule_fixed:
            for cmd in ai.get("commands",[]): print(f"  {col('$',GRAY)} {cmd}")
            return False
    return rule_fixed

def get_steps(port,username,password):
    ah=os.path.expanduser("~/airflow")
    return [
        {"id":1,"critical":True,"name":"Verify Python and pip","cmds":["python3 --version","pip3 --version","df -h | head -3","free -h"],"env":{}},
        {"id":2,"critical":True,"name":"Install Apache Airflow 2.8.0","cmds":['pip3 install "apache-airflow==2.8.0" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.0/constraints-3.8.txt"'],"env":{"AIRFLOW_HOME":ah}},
        {"id":3,"critical":True,"name":"Verify Airflow Binary","cmds":["airflow version"],"env":{"AIRFLOW_HOME":ah}},
        {"id":4,"critical":True,"name":"Initialize Database","cmds":["airflow db init"],"env":{"AIRFLOW_HOME":ah}},
        {"id":5,"critical":False,"name":f"Check Port {port}","cmds":[f"fuser {port}/tcp 2>/dev/null && echo 'WARNING: Port in use!' || echo 'Port {port} FREE'"],"env":{}},
        {"id":6,"critical":True,"name":"Create Admin User","cmds":[f"airflow users create --username {username} --firstname Admin --lastname User --role Admin --email admin@airflow.com --password {password}"],"env":{"AIRFLOW_HOME":ah}},
        {"id":7,"critical":True,"name":f"Start Webserver Port {port}","cmds":[f"airflow webserver --port {port} --daemon"],"env":{"AIRFLOW_HOME":ah}},
        {"id":8,"critical":False,"name":"Start Scheduler","cmds":["airflow scheduler --daemon"],"env":{"AIRFLOW_HOME":ah}},
        {"id":9,"critical":False,"name":"Wait 15s for Boot","cmds":["echo 'Waiting...'","sleep 15"],"env":{}},
        {"id":10,"critical":False,"name":"Health Check","cmds":[f"curl -s http://localhost:{port}/health || echo 'Still booting'"],"env":{"AIRFLOW_HOME":ah}},
    ]

def get_user_inputs():
    section("CONFIGURATION")
    while True:
        port=input(col("  Port [default 8080]: ",CYAN)).strip() or "8080"
        if port.isdigit() and 1024<=int(port)<=65535: break
        print(col("  Enter valid port 1024-65535",YELLOW))
    while True:
        username=input(col("  Admin Username [default admin]: ",CYAN)).strip() or "admin"
        if len(username)>=3: break
        print(col("  3+ characters required",YELLOW))
    while True:
        password=getpass.getpass(col("  Admin Password (hidden): ",CYAN))
        if len(password)>=6: break
        print(col("  6+ characters required",YELLOW))
    print(f"\n  {col('Port    :',GRAY)} {col(port,GREEN,True)}")
    print(f"  {col('Username:',GRAY)} {col(username,GREEN,True)}")
    print(f"  {col('URL     :',GRAY)} {col(f'http://localhost:{port}',BLUE,True)}")
    go=input(col("\n  Press ENTER to start (or n to cancel): ",YELLOW)).strip().lower()
    if go=="n": sys.exit(0)
    return port,username,password

def run_installer(port,username,password):
    steps=get_steps(port,username,password)
    total=len(steps)
    base={"AIRFLOW_HOME":os.path.expanduser("~/airflow")}
    failed,skipped=[],[]
    section(f"PHASE 2 — INSTALLATION ({total} steps)")
    for step in steps:
        sid,sname=step["id"],step["name"]
        env={**base,**step.get("env",{})}
        log_step(sid,sname,total)
        err_out=""; failed_flag=False
        for cmd in step["cmds"]:
            ok_r,out=run_live(cmd,env)
            if not ok_r: failed_flag=True; err_out=out; break
        if not failed_flag: log_ok(f"Step {sid} complete"); continue
        log_warn(f"Step {sid} failed — activating error handler...")
        fixed=handle_error(err_out,sname,port,username,password)
        if fixed:
            log_info(f"Retrying Step {sid}...")
            retry=True
            for cmd in step["cmds"]:
                ok_r,out=run_live(cmd,env)
                if not ok_r: retry=False; break
            if retry: log_ok(f"Step {sid} fixed!")
            else:
                log_err(f"Step {sid} still failing."); failed.append(sid)
                if step.get("critical"): break
        else:
            if step.get("critical"): failed.append(sid); break
            else: skipped.append(sid)
    return failed,skipped

def print_report(port,username,failed,skipped,elapsed):
    section("PHASE 4 — REPORT")
    if not failed:
        print(col("\n  APACHE AIRFLOW IS READY!",GREEN,True))
        print(f"\n  {col('URL     :',WHITE,True)} {col(f'http://localhost:{port}',BLUE,True)}")
        print(f"  {col('Username:',WHITE,True)} {col(username,GREEN)}")
        print(f"  {col('Commands:',WHITE,True)}")
        print(f"  {col('List DAGs:',GRAY)} airflow dags list")
        print(f"  {col('Stop all :',GRAY)} pkill -f airflow")
    else:
        print(col(f"\n  Failed steps: {failed}. Re-run: python3 airflow_agent.py",YELLOW))
    if skipped: print(f"  Skipped: {skipped}")
    print(f"\n  Total time: {elapsed}s")
    divider("═")

def main():
    banner()
    global GROQ_API_KEY
    if not GROQ_API_KEY:
        key=input(col("  Enter Groq API key (or Enter for Rule Engine only): ",CYAN)).strip()
        if key: GROQ_API_KEY=key; os.environ["GROQ_API_KEY"]=key
    rc=len(get_all_rules_summary())
    print(f"\n  {col('Rule Engine:',WHITE,True)} {col(f'{rc} rules loaded',GREEN)}")
    print(f"  {col('Groq AI    :',WHITE,True)} {col('Connected',GREEN) if GROQ_API_KEY else col('Disabled',YELLOW)}")
    all_ok,_=run_all_checks()
    if not all_ok: log_err("Prerequisites failed."); sys.exit(1)
    port,username,password=get_user_inputs()
    start=time.time()
    failed,skipped=run_installer(port,username,password)
    elapsed=round(time.time()-start,1)
    print_report(port,username,failed,skipped,elapsed)

if __name__=="__main__":
    main()
