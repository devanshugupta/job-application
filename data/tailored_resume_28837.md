Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer at Amazon Prime Video running production data pipelines, retrieval infrastructure, and evaluation systems for 1M+ users, with earlier terabyte-scale Spark and Airflow ETL at TCS; first-author EMNLP 2025 researcher.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Recovered 117 dropped web sources/day for LLM grounding by redesigning web-source parsing with attribution gating and domain fallback, eliminating blank source cards in production.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race that drove intermittent pipeline failures to zero.
- Led a five-team cross-org data contract joining explicit and voice feedback to assistant sessions, authoring the analytics table schema and validating joins with Athena SQL against live data.
- Optimized query-time retrieval and bounded conversation caching to 5 turns, cutting cache payload 75% and memory 40% under peak traffic.
- Shipped semantic query-to-title retrieval with multilingual E5 embeddings on a SageMaker endpoint and ANN/kNN search over a FAISS index, feature-flagged with a 750ms timeout and fail-open rollout.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Bash
ML: PyTorch, TensorFlow, scikit-learn, Koog
Data: Spark, PySpark, Airflow, Kafka, ETL Pipelines
Systems: Docker, Kubernetes, Linux, CI/CD (Jenkins)
Cloud: AWS (S3, Lambda, SageMaker, CloudWatch), Azure (ADLS, Databricks)