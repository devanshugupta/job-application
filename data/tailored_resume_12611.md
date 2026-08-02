Devanshu Gupta
dgupta77@asu.edu |
623-290-3858 | linkedin.com/in/devanshu0gupta
| github.com/devanshugupta
## Summary
ML engineer at Amazon Prime Video building real-time NLP and LLM systems: fine-tuned models, automated LLM evaluation at 50K conversations/day, and low-latency Python inference serving 1M+ users.
## Research Publications
Weaver: Interweaving SQL and LLM for Table Reasoning [EMNLP 2025 - First Author]
TraceBack: Multi-Agent Decomposition for Fine-Grained Table Attribution [TACL 2026, under review]
## Work Experience
### Amazon, Prime Video | Machine Learning Engineer (06/2025 -- Present)
- Developed a multi-turn LLM evaluation framework processing 50K+ conversations/day with LLM-as-judge and automated accuracy validation, increasing defect discovery 60%.
- Trained a LoRA fine-tuned LLM as a production query router, improving relevance 5% and cutting latency 50%; adopted for production.
- Launched real-time semantic inference with multilingual E5 embeddings on a SageMaker endpoint under a 750ms timeout with fail-open for zero live-turn degradation.
- Reworked a safety classifier from keyword to intent-based detection with bias-aware validation across 50-run regression batches, preserving legitimate content with zero false negatives.
- Optimized real-time serving by moving candidate filtering ahead of metadata fetch and bounding cache to 5 turns, cutting payload 75% and memory 40% under peak load.
### Tata Consultancy Services | Software Engineer (08/2021 -- 08/2023)
- Maintained Azure Data Lake Storage (ADLS Gen2) architecture storing terabytes of distributed data, ensuring high availability and scalable ingestion.
- Raised batch pipeline throughput 40% by optimizing the transformation, ingestion, and validation stages across production systems.
- Created Tableau dashboards on user-behavior metrics, surfacing actionable insights that informed product decisions.
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
Languages: Python, SQL, Kotlin
ML/NLP: PyTorch, TensorFlow, scikit-learn, Koog, Fine-tuning (LoRA/PEFT), Model Evaluation, Classification, Bias Analysis
LLM: RAG, Prompt Engineering, LLM-as-judge, Amazon Bedrock
Serving: SageMaker, FAISS, Low-latency Inference, AWS