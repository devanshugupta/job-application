Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer at Amazon Prime Video shipping production LLM and retrieval services for 1M+ users under hard latency, quality, and cost budgets. First-author EMNLP 2025 researcher.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped an embedding retrieval and ranking service (FAISS, ANN/kNN) for 1M+ users at 0.5s end-to-end latency, lifting CTR 16% through offline and online evaluation.
- Led a production assistant's migration to a new Amazon Bedrock model with reserved-throughput overrides and A/B-gated prompt regression testing, owning quality, latency, and cost tradeoffs.
- Deployed semantic retrieval on a SageMaker endpoint with multilingual E5 embeddings, feature-flagged with a 750ms timeout and fail-open behavior for zero live-turn degradation.
- Scaled backend REST and gRPC services for Alexa voice integration to 100K+ queries daily under a 300ms SLA, improving P99 latency 3x by parallelizing downstream calls.
- Owned deployment reliability with service-level auto-rollback alarms and a functional deep health check, root-causing a grace-period race and driving intermittent failures to zero.
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
Languages: Python, SQL, Kotlin, Java, C++
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, LoRA Fine-tuning
Serving & LLM: SageMaker, Bedrock, Model Deployment, Latency Optimization, FAISS, Vector Search, RAG, Reranking
Systems: REST, gRPC, Microservices, Docker, Kubernetes, CI/CD, Caching
Cloud: AWS (EC2, S3, Lambda, SQS, Step Functions, CloudWatch)