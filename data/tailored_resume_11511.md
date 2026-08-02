Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML Engineer at Amazon Prime Video building production search, ranking, and recommendation systems serving 1M+ users. First-author EMNLP 2025 researcher in vector search, hybrid retrieval, and text understanding at consumer scale.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for 'Similar to X' recommendations serving 1M users at 0.5s latency, improving CTR 16%.
- Developed semantic query-to-title retrieval with multilingual E5 embeddings on a SageMaker endpoint and ANN/kNN over a FAISS index, feature-flagged with a 750ms timeout and fail-open.
- Rolled out hybrid retrieval with an XGBoost classifier routing queries to parallel OpenSearch and catalog retrievers with multi-turn LLM reranking, improving relevance 5% and cutting latency 50%.
- Resolved double-counted feedback events with latest-per-turn deduplication and fixed 3x session-table duplication, with no query-time regression confirmed by benchmarking.
- Delivered a multi-turn LLM evaluation framework processing 50K+ conversations/day with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### Hybrid Music Recommender ()
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals and cold-start handling for new tracks.
### Image Search Engine ()
- Built end-to-end image search on 10K images using clustering and LSH vector indexing, reducing nearest-neighbor retrieval time from 1 hour to 30 seconds.
## Education
### Master of Science in Computer Science Arizona State University, Tempe, AZ, USA
05/2025 · GPA: 3.9/4
Coursework: Statistical Machine Learning, Cloud Computing, Data Mining, NLP, Multimedia & Web databases
### Bachelor of Technology in Computer Science & Engineering University Institute of Technology RGPV, India
06/2021 · GPA: 8.4/10
## Technical Skills
Languages: Python, Java, SQL, Kotlin
ML: PyTorch, TensorFlow, scikit-learn, Koog, Ranking (NDCG, Recall@K), Recommender Systems, Fine-tuning (LoRA)
Retrieval & NLP: FAISS, Vector Search, Hybrid Retrieval, Semantic Search, RAG, LLMs