**Product Requirements Document (PRD): LiNKautowork Automation Engine**

**Version:** 1.1

**Status:** Updated Blueprint

**Date:** March 19, 2026

## ---

**1\. Executive Summary**

**LiNKautowork** is the "Autonomous Nervous System" of the LiNKtrend ecosystem. It is a productized automation engine that researches, builds, manages, and self-refines JSON-based workflows primarily via n8n. Governed by specialized LiNKbots utilizing the **Karpathy Self-Research Method**, it ensures all automations are deterministic and high-performance. It serves as the execution bridge between LiNKskills (logic), LiNKsites/apps (interfaces), and LiNKbrain (memory).

## ---

**2\. Business Logic & Monetization Layer**

### **2.1 The "Automated Utility" Thesis**

To achieve a near-zero marginal cost of digital venture creation, manual workflow intervention is eliminated. Automations are treated as liquid assets and modular infrastructure.

### **2.2 Revenue & Delivery Models**

* **Internal Utility:** Powers LiNKtrend studio operations and internal departmental OKRs.

* **Embedded Logic:** Integrated into LiNKbots, LiNKsites, or LiNKapps as native features.

* **Managed Service (SaaS):** High-value n8n workflows hosted on LiNKtrend infrastructure for external clients.

* **Automation Packs (IP Sale):** One-time sale of proprietary JSON workflow files for client-hosted instances.

* **Logic Subscription:** Access to premium automations via the LiNKskills Gateway API.

### **2.3 Client Data Isolation Requirements**

To support external monetization, the system must enforce strict multi-tenancy:

* **Logical Isolation:** Every client execution must be tagged with a unique tenant\_id.

* **Database Security:** Implementation of Row-Level Security (RLS) on the audit\_runs table in Supabase ensures Client A cannot access Client B's metadata or error logs.

* **Secret Management:** Client-specific API credentials must be retrieved Just-In-Time (JIT) from Google Secret Manager; no keys are stored within the JSON schema.

## ---

**3\. The Automation Anatomy**

A LiNKautowork "Unit" consists of four interconnected layers:

| Component | Description | Technical Requirement |
| :---- | :---- | :---- |
| **Workflow (JSON)** | The executable n8n schema. | Version-controlled; supports environment variables. |
| **Telemetry Hook** | The "Sensor" reporting to LiNKbrain. | Logs success/failure/latency to audit\_runs. |
| **Research Doc** | The "Genesis" file. | Documentation of need, competitors, and ROI. |
| **Evals Suite** | The "Testing" layer. | Synthetic inputs used to validate deployment. |

## ---

**4\. Operational Framework & Promotion Path**

### **4.1 The Autoworker Squad (LiNKbots)**

The engine is managed by specialized agents operating under the "Senior Sovereign" persona:

* **The Scout (Discovery):** Researches trending automation needs and market signals.

* **The Architect (n8n Engineer):** Generates JSON workflows and configures node logic.

* **The Auditor (QA):** Executes the Karpathy Self-Research loop and synthetic evals.

* **The Maintainer (Reliability):** Monitors LiNKbrain for drift and triggers self-healing.

### **4.2 The Karpathy Self-Research Loop**

1. **Phase 1: Zero-Shot Construction:** Architect builds the MVP workflow.

2. **Phase 2: Stress-Testing:** Auditor generates 100+ "Dirty Data" scenarios.

3. **Phase 3: Failure Forensic:** Auditor identifies non-deterministic break points.

4. **Phase 4: Optimization:** Architect rewrites logic for 100% pass rate.

### **4.3 Global Skill Library (LiNKskills) Promotion Path**

When an automation is proven successful within a specific venture, it follows a deterministic path to become a Studio-wide asset:

* **Trigger:** LiNKbrain identifies a sequence successful across five distinct ventures.

* **Validation:** The Head of Quality Standards audits the workflow against the "Definition of Done" (DoD).

* **Standardization:** The Architect refines the JSON into a modular, reusable "LiNKskill".

* **Deployment:** The skill is uploaded to the centralized server, making it dynamically loadable by all LiNKbots.

## ---

**5\. Review Rituals & Governance**

### **5.1 Operational Gate (Review \#2)**

The **Operational Gate** occurs daily at **10:45 Taipei Time**. The COO manages the **Paperclip Orchestrator** to generate an automated "Operational Pulse Report" for the Principal:

* **Cost Audit:** Global token usage and API costs per venture.

* **Health Metrics:** n8n execution success rates and error traces.

* **Confidence Flags:** Any decision or automation performance reporting \<80% certainty.

## ---

**6\. Technical Architecture**

### **6.1 Hosting & Environment**

* **Platform:** Self-hosted n8n instance on DigitalOcean.

* **Memory:** LiNKbrain (pgvector on Supabase) stores all experiences and deployment logs.

* **Gateway:** Integration with LiNKskills for Remote Procedure Execution (RPE).

### **6.2 Security & Risk Management**

* **The Kill Switch:** Global revocation of webhooks if token consumption or rate limits exceed safety thresholds.

* **Emergency Protocol:** Critical logic contradictions trigger an immediate \[CRITICAL ERROR: EXECUTION HALTED\] status.

## ---

**7\. Development Roadmap (The Gates)**

* **Phase 1: MVO (Foundational Control):** Stable n8n instance with manual creation and LiNKbrain logging .

* **Gate 1: Autonomous Refinement:** Activation of the Karpathy Loop; bots edit JSON via API to fix known errors .

* **Gate 2: The Marketplace:** Public-facing API for "Automation-as-a-Service" with \<60 second provisioning .

