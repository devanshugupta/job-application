Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Software engineer at Amazon Prime Video building distributed data and ML services on AWS for 1M+ users, with prior terabyte-scale Spark and Airflow pipeline work at Tata Consultancy Services.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Drove a five-team cross-org data contract joining explicit and voice feedback into assistant analytics, authoring the table schema and validating joins with Athena SQL against live data.
- Led backend REST and gRPC services for Alexa voice integration serving 100K+ queries daily under a 300ms SLA, improving P99 latency 3x by parallelizing downstream calls.
- Resolved double-counted feedback events with latest-per-turn deduplication and fixed 3x session-table duplication, confirming no query-time regression through benchmarking.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding conversation cache to five turns, cutting cache payload 75% and memory 40% at peak.
- Hardened deployments with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race and driving intermittent production failures to zero.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Java, C++
Data: Spark, PySpark, Kafka, Airflow, Athena, ETL/ELT, PostgreSQL, DynamoDB, Redis
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost
Systems: Distributed Systems, REST, gRPC, Microservices, Event-Driven, SQS, Caching, Kubernetes, Docker
Cloud: AWS (EC2, S3, Lambda, SQS, Step Functions, CloudWatch), Azure (ADLS, Databricks)