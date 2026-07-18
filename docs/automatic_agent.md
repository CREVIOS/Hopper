Act as an expert Senior Cloud Architect and AI Engineer. I need to add two major features to my existing project: a suite of free-tier open-source agents, and an always-on telemetry/monitoring agent that sends reports to WhatsApp or email. 

Please provide the complete, modular code structure, setup instructions, and deployment steps based on the following specifications:

---

### FEATURE 1: Free Open-Source Agent Layer (Hermes, Clawbot, OpenCode)
I want to deploy and interact with open-source agents (Hermes, OpenCode, and general coding/robotic reasoning models like Clawbot equivalents) completely for free. 
- **Requirement:** Do NOT use paid APIs (No OpenAI, No Anthropic paid tiers).
- **Implementation Strategy:** Implement a flexible adapter/provider pattern in Python. 
  - Provide a configuration that defaults to **Groq** (using their free tier API for models like Llama/Mixtral) or **Hugging Face Serverless Inference API** (completely free for open models).
  - Also provide a fallback to a local **Ollama** setup (`localhost:11434`) for when I want to run them locally for free.
- **Deliverable:** A `free_agents.py` file containing the classes or functions to initialize and invoke `HermesAgent`, `ClawbotAgent`, and `OpenCodeAgent` using these free engines.

---

### FEATURE 2: Always-On Telemetry Agent (LangGraph or CrewAI)
I need a dedicated background agent that is "always onboarded," continuously checks system telemetry/application logs, and sends a summary report directly to me via Telegram, WhatsApp or Email.
- **Orchestration:** Use LangGraph (preferred for stateful, cyclic monitoring loops) or CrewAI.
- **Functionality:** 
  1. **Fetch Telemetry Data:** A mock or real tool function that reads application performance metrics (CPU, memory, error rates, or database row counts).
  2. **Analyze:** The agent evaluates if things are running smoothly or if errors are spiking.
  3. **Alerting System:** Implement an alerting utility using:
     - **Email:** The `resend` Python library (using Resend's generous free tier) OR standard `smtplib` with a free Gmail App Password.
     - **WhatsApp:** A webhook structure using the Twilio Sandbox or Green API (free tiers).
- **Continuous Execution:** Explain exactly how to run this script as a lightweight background worker/cron job (e.g., using `apscheduler` in a background thread, or deploying it to a free hosting tier like Render/Railway).
- **Deliverable:** A `telemetry_agent.py` file orchestrating this agent and its execution loop.

---