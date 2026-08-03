Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Software engineer at Amazon Prime Video shipping production backend services and ML features end to end. First-author EMNLP 2025 researcher; MS CS 3.9, strong on testing, reliability, and ownership.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Led Alexa voice integration for Prime Video as backend REST and gRPC services serving 100K+ queries/day under a 300ms SLA, improving P99 latency 3x under peak load.
- Established unit and integration test frameworks that raised service validation coverage to 90%, improving production deployment reliability.
- Hardened deployment reliability with service-level auto-rollback alarms and a deep health check, root-causing a grace-period race that drove intermittent failures to zero.
- Eliminated a recurring customer-facing crash (100 occurrences in two weeks) by adding a conditional routing edge to a catalog-search fallback.
- Optimized query-time retrieval by reordering candidate filtering ahead of metadata fetch and bounding cache to 5 turns, cutting cache payload 75% and memory 40%.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
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
Languages: Python, SQL, Kotlin, Java, C++
Backend: REST APIs, gRPC, Microservices, Distributed Systems, Caching
Data: PostgreSQL, DynamoDB, Redis, Spark
Systems: Docker, Kubernetes, CI/CD (Jenkins), AWS, Git