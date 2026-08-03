Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Backend engineer at Amazon Prime Video building distributed, high-concurrency services and trust-and-safety systems, with big-data pipeline experience across Spark and Airflow.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Reworked a trust-and-safety filter from keyword to intent-based detection, closing a content-bypass gap while preserving legitimate queries, validated with zero false negatives.
- Led backend gRPC and REST services serving 100K+ queries/day under 300ms SLA, parallelizing downstream calls to improve P99 latency 3x under peak load.
- Drove a five-team cross-org data contract joining feedback signals to sessions, authoring the analytics-table schema and validating joins with Athena SQL against live data.
- Eliminated a recurring customer-facing crash (100 occurrences in two weeks) by adding a conditional agent-graph edge routing empty-title prompts to a catalog-search fallback.
- Established a multi-turn evaluation framework processing 50K+ conversations/day with automated fact validation, increasing defect discovery 60% for risk insight.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
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
Languages: Python, Java, C++, SQL, Kotlin
Backend: gRPC, REST, microservices, message queues (Kafka), distributed systems, high concurrency, caching
Big Data: Spark, PySpark, Airflow, Athena
Trust & Safety: intent detection, content moderation
ML: scikit-learn, PyTorch