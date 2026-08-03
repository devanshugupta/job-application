Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Backend engineer at Amazon Prime Video building scalable REST and gRPC microservices serving 100K+ queries/day under strict latency SLAs, with production reliability and caching ownership.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Led Alexa voice integration as backend REST and gRPC services serving 100K+ queries/day under a 300ms SLA, parallelizing downstream calls to improve P99 latency 3x under peak load.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding conversation cache to 5 turns, cutting cache payload 75% and memory 40% under peak traffic.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race that drove intermittent failures to zero.
- Eliminated a recurring customer-facing crash (100 occurrences in two weeks) by adding a conditional agent-graph edge routing empty-title prompts to a catalog-search fallback.
- Established unit and integration test frameworks that raised service validation coverage to 90%, improving production deployment reliability.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
## Projects
### Elastic AWS Cloud Application for Face Recognition |
- Developed auto-scaling AWS (EC2, ELB, SQS, S3) Flask REST system handling 1,000 concurrent requests with 30-second elastic shutdown for cost-efficient scaling.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, Java
Backend: REST, gRPC, Microservices, API Gateway, Distributed Systems, Event-Driven, Caching
Data: PostgreSQL, DynamoDB, Redis, Kafka
Systems: Kubernetes, Docker, CI/CD, AWS (Lambda, Step Functions, CloudWatch)