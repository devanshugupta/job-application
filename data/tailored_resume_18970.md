Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video building production LLM inference, agent routing, and evaluation infrastructure at consumer scale. First-author EMNLP 2025 researcher; MS CS 3.9.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Trained a LoRA fine-tuned query router for a hybrid retrieval inference system, improving relevance 5% and cutting latency 50%; won internal hackathon and adopted for production.
- Eliminated a recurring agent crash by adding a conditional agent-graph edge routing empty-title prompts to a fallback, hardening the agent infrastructure across 10+ features.
- Optimized query-time inference by reordering candidate filtering ahead of metadata fetch and bounding cache to 5 turns, cutting cache payload 75% and memory 40% under peak load.
- Migrated the assistant backend to a new Bedrock model with reserved-throughput overrides and A/B-gated regression testing, owning the production model lifecycle.
- Developed a multi-turn LLM evaluation framework processing 50K+ conversations/day with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, C++
ML: PyTorch, TensorFlow, scikit-learn, Koog, Fine-tuning (LoRA/PEFT), Model Evaluation
LLM Infra: Inference serving, RAG, Agent routing, Bedrock, SageMaker
Systems: Docker, Kubernetes, gRPC