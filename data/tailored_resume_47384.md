Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
Machine Learning Engineer at Amazon Prime Video shipping search retrieval, ranking, and evaluation systems for 1M+ users. First-author EMNLP 2025 research on combining LLMs with structured search.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Shipped an embedding retrieval and ranking pipeline (FAISS, ANN/kNN, NDCG) powering Similar-to-X recommendations for 1M+ users at 0.5s end-to-end latency, lifting CTR 16%.
- Trained an XGBoost ranker capturing interactions between query signals to route across parallel OpenSearch and catalog retrievers with multi-turn LLM reranking, improving relevance 5% and cutting latency 50%.
- Domain-adapted a LoRA fine-tuned language model as the hybrid retrieval query router, matching catalog vocabulary in production, and won the internal hackathon with the approach.
- Led semantic query understanding with multilingual E5 embeddings on SageMaker and ANN search over a FAISS index, feature-flagged with a 750ms timeout for zero live-turn degradation.
- Owned a multi-turn LLM evaluation framework processing 50K+ conversations daily with LLM-as-judge and automated fact validation, increasing defect discovery 60%.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
- Built scalable demand forecasting pipeline using Spark in Databricks and XGBoost, cutting supply chain costs by $4M.
- Designed distributed data pipelines on Airflow integrating 4+ data sources into unified storage, improving data consistency.
## Projects
### AdPrompter: Generative AI for Ads |
- Built the backend and rating components of an RL pipeline generating 50+ multimodal ad variants/product, improving Click Through Rate 25% with bias detection and text-to-video extensibility.
### Hybrid Music Recommender |
- Built a content-based recommender over 10K songs using 30 audio and metadata features (MFCC, spectral, tempo) with collaborative-filtering signals, a MySQL history store, and cold-start handling for new tracks.
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
ML: PyTorch, TensorFlow, scikit-learn, Koog, XGBoost, LoRA Fine-tuning, Ranking Systems
Search & Retrieval: FAISS, OpenSearch, Vector Search, Hybrid Retrieval, Query Understanding, RAG, Reranking
Evaluation: NDCG, Recall@K, LLM-as-Judge, A/B Experimentation, PromptFoo
Cloud: AWS, SageMaker, Kubernetes, Docker, Spark