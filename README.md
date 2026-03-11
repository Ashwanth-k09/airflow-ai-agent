# Airflow AI Installer Agent
Powered by Groq AI + Rule Engine

## Run
```bash
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here
python3 airflow_agent.py
```

## How it works
1. Asks for port, username, password
2. Runs 13 installation steps
3. On error: Rule Engine checks 30+ patterns → Groq AI analyses → auto-fix applied → step retried
