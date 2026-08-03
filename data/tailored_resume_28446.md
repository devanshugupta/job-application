Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML Engineer at Amazon Prime Video building large-scale retrieval, ranking, and experimentation systems serving 1M+ users, with production A/B rollout ownership and a first-author EMNLP 2025 publication.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped an embedding-based retrieval and ranking pipeline serving recommendations to 1M+ users at 0.5s end-to-end latency, lifting CTR 16% through offline and online evaluation.
- Owned hybrid retrieval system design with an XGBoost query router across parallel retrievers and LLM reranking, improving relevance 5% and cutting latency 50%, adopted for production.
- Led backend gRPC and REST services for a voice integration serving 100K+ queries daily under a 300ms SLA, parallelizing downstream calls for 3x P99 improvement.
- Invented a feature-gating and A/B experimentation framework adopted team-wide, enabling controlled rollouts and fast data-driven iteration across 10+ production AI features.
- Optimized query-time retrieval and conversation caching under peak traffic, cutting cache payload 75% and memory 40% while eliminating stale-result recommendation risk.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Elastic AWS Cloud Application for Face Recognition |
- Architected auto-scaling AWS (EC2, ELB, SQS, S3) Flask-based REST system handling 1,000 concurrent requests, enabling 30-second elastic shutdown and improved cost-efficient scaling.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, Java, C++, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, ranking
Retrieval: FAISS, vector search, embeddings, reranking
Systems: gRPC, distributed systems, caching, A/B experimentation
Cloud: AWS, SageMaker, Docker, Kubernetes