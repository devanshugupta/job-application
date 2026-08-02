Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Backend engineer at Amazon Prime Video building REST and gRPC services and data pipelines for assistant features serving 1M+ users. First-author EMNLP 2025 researcher with agent-infrastructure and retrieval systems experience.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Led Alexa voice integration for Prime Video as backend REST and gRPC services serving 100K+ queries/day under a 300ms SLA, parallelizing downstream calls to improve P99 latency 3x.
- Drove a five-team cross-org data contract joining explicit and voice feedback to assistant sessions, authoring the analytics-table schema and validating joins with Athena SQL against live data.
- Eliminated a recurring customer-facing crash, 100 occurrences in two weeks, by adding a conditional agent-graph edge routing empty-title prompts to a catalog-search fallback.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding conversation cache to five turns, cutting cache payload 75% and memory 40% under peak traffic.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race that drove intermittent failures to zero.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
## Projects
### Elastic AWS Cloud Application for Face Recognition |
- Delivered an auto-scaling AWS (EC2, ELB, SQS, S3) Flask REST system handling 1,000 concurrent requests with 30-second elastic shutdown for cost-efficient scaling.
### Image Search Engine ()
- Developed an image search system over 10K images using clustering and LSH vector indexing, cutting nearest-neighbor retrieval from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Java
Backend: REST APIs, gRPC, Microservices, Distributed Systems, PostgreSQL, DynamoDB, Kafka, Airflow, Spark
ML: PyTorch, TensorFlow, scikit-learn, Koog
Cloud: AWS, Docker, Kubernetes