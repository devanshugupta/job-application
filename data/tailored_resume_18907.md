Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video building large-scale retrieval and ranking systems serving 1M users, improving CTR through offline/online evaluation and A/B experimentation.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped an embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for recommendations serving 1M users at 0.5s latency, improving CTR 16% via offline/online evaluation.
- Developed hybrid retrieval with an XGBoost classifier routing queries to parallel retrievers with multi-turn reranking, improving relevance 5% and cutting latency 50%.
- Trained a LoRA fine-tuned query router for the hybrid ranking system, improving relevance 5% and cutting latency 50%; won internal hackathon and adopted for production.
- Rolled out a feature gating and A/B experimentation framework enabling controlled rollouts and repeatable experiments across 10+ production AI features.
- Led backend gRPC and REST services serving 100K+ queries/day under 300ms SLA, parallelizing downstream calls to improve P99 latency 3x under peak load.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
## Projects
### AdPrompter: Generative AI for Ads ()
- Developed the backend and rating components of an RL pipeline generating 50+ multimodal ad variants per product, improving Click Through Rate 25% with bias detection.
### Hybrid Music Recommender ()
- Delivered a content-based recommender over 10K songs using 30 audio and metadata features with collaborative-filtering signals and cold-start handling for new tracks.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, C++, Java, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, Ranking (NDCG, Recall@K), CTR modeling, LoRA fine-tuning
Retrieval: FAISS, OpenSearch, vector search, reranking
Backend: gRPC, REST, microservices, A/B experimentation