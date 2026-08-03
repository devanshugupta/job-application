Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML Engineer at Amazon Prime Video building production agentic LLM systems, RAG pipelines, and evaluation infrastructure serving 1M+ users, with LoRA fine-tuning experience and a first-author EMNLP 2025 publication.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Led migration of a production agentic assistant backend to a new Amazon Bedrock model with reserved throughput, A/B-gated prompt regression testing, and hardened tool routing, owning the model lifecycle.
- Eliminated a recurring customer-facing crash by adding a conditional agent-graph edge routing empty-prompt turns to an agentic catalog-search fallback, now firing weekly with zero customer errors.
- Improved RAG grounding by redesigning web-source parsing with attribution gating and domain fallback, recovering 117 dropped results daily and eliminating blank source cards in production.
- Developed a multi-turn LLM evaluation framework processing 50K+ conversations daily with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
- Trained a LoRA fine-tuned routing model for hybrid retrieval, improving relevance 5% and cutting latency 50%, adopted for production.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, LoRA fine-tuning
Agents: LangChain, agent orchestration, tool use, RAG, prompt engineering
Evaluation: LLM-as-judge, promptfoo, A/B testing
Cloud: AWS, Bedrock, SageMaker, Docker