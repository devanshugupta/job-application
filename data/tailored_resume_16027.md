Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Backend engineer at Amazon Prime Video building distributed services and policy-driven access controls: server-side enforcement gates, intent-based safety filtering, and reliability engineering for services at 1M+ user scale.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Built a server-side fail-closed access gate enforcing profile-based policy (anything not permitted is restricted) with a blocked-request metric, blocking 120 unauthorized requests/week in production.
- Reworked a content-policy filter from keyword to intent-based enforcement, closing a bypass gap while preserving legitimate access, validated across 50-run regression batches with zero false negatives.
- Led backend service integration as REST and gRPC microservices serving 100K+ queries/day under a 300ms SLA, parallelizing downstream calls to improve P99 latency 3x.
- Instrumented enforcement observability with dedicated trace types and CloudWatch metrics (called/success/blocked/timeout/failure), keeping policy behavior continuously verifiable.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, driving intermittent production failures to zero.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
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
Languages: Python, SQL, Kotlin, Java
Backend: REST APIs, gRPC, Microservices, Distributed Systems, Access Control, Policy Enforcement, Caching
Data: PostgreSQL, DynamoDB, Redis, Athena SQL
Reliability: Observability, CloudWatch, Auditability, A/B Testing
Cloud: AWS, Docker