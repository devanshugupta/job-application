Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine learning engineer at Amazon Prime Video building and deploying production retrieval, ranking, and LLM evaluation systems end to end for 1M+ users. First-author EMNLP 2025 researcher with fine-tuning and MLOps experience.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped an embedding-based retrieval and ranking pipeline (FAISS, KNN, NDCG) for recommendations serving 1M users at 0.5s latency, improving CTR 16% via offline and online evaluation.
- Developed a multi-turn LLM evaluation framework processing 50K+ conversations/day with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
- Launched hybrid retrieval with an XGBoost classifier routing queries to parallel OpenSearch and catalog retrievers with LLM reranking, improving relevance 5% and cutting latency 50%.
- Trained a LoRA fine-tuned model as the query router for the hybrid retrieval system, improving relevance 5% and cutting latency 50%, adopted for production after winning an internal hackathon.
- Optimized query-time retrieval by moving candidate filtering ahead of metadata fetch and bounding conversation cache to five turns, cutting cache payload 75% and memory 40% under peak traffic.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Automated data-quality validation and monitoring across ETL workflows, halving production pipeline failures.
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
## Projects
### Hybrid Music Recommender ()
- Modeled a content-based recommender over 10K songs using 30 audio and metadata features with collaborative-filtering signals and cold-start handling for new tracks.
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
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, LoRA/PEFT, MLflow, Model Evaluation
Retrieval/LLM: FAISS, OpenSearch, Vector Search, RAG, Reranking
Infra: Airflow, Docker, Kubernetes, AWS SageMaker, PostgreSQL, CI/CD