Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML systems engineer at Amazon Prime Video running production model-serving and retrieval at 1M-user scale, focused on latency, deployment reliability, and cost-efficient inference.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Migrated the assistant serving backend to a new Bedrock model with reserved-throughput overrides and A/B-gated regression testing, owning the production model lifecycle end-to-end.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race that drove intermittent failures to zero.
- Optimized query-time inference by moving candidate filtering ahead of metadata fetch and bounding conversation cache to 5 turns, cutting cache payload 75% and memory 40% under peak.
- Led Alexa integration as backend REST and gRPC services serving 100K+ queries/day under 300ms SLA, parallelizing downstream calls to improve P99 latency 3x under peak load.
- Shipped semantic retrieval on a SageMaker endpoint feature-flagged with a 750ms timeout and fail-open, achieving zero live-turn degradation in production.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
## Projects
### Elastic AWS Cloud Application for Face Recognition |
- Developed an auto-scaling AWS (EC2, ELB, SQS, S3) Flask REST system handling 1,000 concurrent requests with 30-second elastic shutdown, improving cost-efficient scaling.
### Image Search Engine ()
- Delivered an image search system over 10K images using clustering and LSH vector indexing, cutting nearest-neighbor retrieval from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, SageMaker serving
Serving/Infra: FAISS, OpenSearch, model lifecycle, Kubernetes, Docker, CI/CD, gRPC
Cloud: AWS, CloudWatch