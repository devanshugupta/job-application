Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video building production retrieval and ranking: bi-encoder embedding search, multi-stage rankers, and cross-encoder reranking serving 1M+ users. First-author EMNLP 2025 on hybrid retrieval and content understanding.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped bi-encoder embedding retrieval and ranking (FAISS, KNN, NDCG) for 'Similar to X' recommendations serving 1M users at 0.5s latency, improving CTR 16% via offline and online evaluation.
- Built a multi-stage ranker: XGBoost query routing across parallel OpenSearch (FAISS) retrievers with multi-turn cross-encoder LLM reranking, improving relevance 5% and cutting latency 50%.
- Launched semantic query-to-title retrieval with multilingual E5 embeddings on a SageMaker endpoint, feature-flagged with a 750ms timeout and fail-open for zero live-turn degradation.
- Developed a 50K-conversation/day evaluation framework with automated quality validation, monitoring model relevance and reliability in production and increasing defect discovery 60%.
- Rolled out feature gating and A/B experimentation for controlled model rollouts across 10+ production ML features.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### Image Search Engine |
- Built end-to-end image search system on 10K images using clustering + LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, Ranking (NDCG, Recall@K), Fine-tuning (LoRA/PEFT)
Retrieval: FAISS, OpenSearch, Bi-encoders, Cross-encoder Reranking, Vector Search, Embeddings, Multi-stage Ranking, RAG
Serving: SageMaker, AWS, A/B Testing