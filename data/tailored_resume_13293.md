Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML Engineer at Amazon Prime Video building low-latency model-serving and MLOps infrastructure (REST/gRPC, CI/CD, auto-rollback) for voice and assistant systems serving 100K+ queries/day under strict SLAs.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Led Alexa voice integration for Prime Video as backend REST and gRPC services serving 100K+ queries/day under 300ms SLA, parallelizing downstream calls to improve P99 latency 3x.
- Hardened deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race that drove intermittent failures to zero.
- Migrated the assistant backend to a new Amazon Bedrock model with reserved-throughput overrides and A/B-gated regression testing, owning the production model lifecycle.
- Rolled out automated regression testing (PromptFoo) with a retry methodology that solved flaky tests, now used team-wide to catch quality regressions before production.
- Optimized query-time serving by moving candidate filtering ahead of metadata fetch and bounding the conversation cache to 5 turns, cutting cache payload 75% and memory 40% under peak traffic.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### Hybrid Music Recommender ()
- Built a content-based recommender over 10K songs using 30 audio features (MFCC, spectral, tempo) with collaborative-filtering signals and cold-start handling for new tracks.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin, C++
ML: PyTorch, TensorFlow, scikit-learn, Koog, Model Serving, Model Evaluation
MLOps: Kubernetes, Docker, CI/CD (Jenkins), Auto-Rollback, Observability (CloudWatch), Autoscaling
Serving: REST, gRPC, SageMaker, Low-Latency Inference