#!/usr/bin/env python3
"""Author the 40 tailoring patches (Claude = the brain), keyed by URL.

Each patch reframes ONLY the candidate's real master content (sde.tex / ml_sde.tex)
toward the JD: a 2-line summary, the top-2 bullets, a truthful Technical Skills block,
and the role-defining `must_haves` used for the honest match metric. Nothing invented.

PATCHES is indexed 0..39 matching data/_selected.json order (20 SDE then 20 ML).
"""
import json, pathlib

sel = json.loads(pathlib.Path("data/_selected.json").read_text())

# ---- 20 SDE patches (indices 0-19) ----------------------------------------- #
P = [None] * 40

P[0] = dict(  # Boeing  Secure Network & Protocols
    summary="Software Engineer at Amazon Prime Video building CI/CD infrastructure and distributed backend services for systems serving 1M+ users, skilled in Linux administration, bash scripting, containerization, and Kubernetes deployment across the end-to-end software development lifecycle.",
    top_bullets=[
        "Owned the CI/CD pipeline and regression test suite for distributed AI services on Linux, triaging build failures and cutting pre-production defects 30% across release cycles.",
        "Containerized and deployed services using Docker and Kubernetes with bash automation and monitoring, hardening reliability for data exchanged across distributed system boundaries.",
    ],
    technical_skills="Languages: Python, Java, C++, Bash/Shell Scripting, SQL\nSystems: Distributed Systems, Linux/Unix, REST APIs, gRPC, Fault Tolerance\nCI/CD and DevOps: Docker, Kubernetes, Containerization, GitHub Actions, Git\nObservability: CloudWatch, Monitoring, Distributed Tracing, Performance Profiling\nCloud: AWS (EC2, S3, Lambda, SQS), Azure",
    must_haves=["linux", "bash|shell scripting", "containerization|docker", "kubernetes",
                "testing|regression", "distributed systems", "lifecycle", "networking|network"],
)
P[1] = dict(  # Coca-Cola  Software Engineer 1
    summary="Software Engineer at Amazon Prime Video delivering end-to-end backend services for distributed systems serving 1M+ users, balancing scalability, reliability, and maintainability while partnering with product and design to ship high-quality features with strong testing, observability, and CI/CD.",
    top_bullets=[
        "Owned end-to-end engineering of AI features for 1M+ users, making pragmatic architecture tradeoffs across speed, scalability, and reliability while partnering closely with product and design.",
        "Drove engineering quality through CI/CD pipelines, regression testing, and CloudWatch observability, cutting pre-production defects 30% and surfacing distributed-system regressions early.",
    ],
    technical_skills="Languages: Python, Java, JavaScript, C++, SQL\nPractices: System Design, Architecture, Agile, Code Review, Testing, CI/CD\nBackend: REST APIs, Distributed Systems, Microservices, gRPC, Fault Tolerance\nObservability: CloudWatch, Monitoring, Distributed Tracing, Performance Profiling\nCloud and DevOps: AWS (EC2, S3, Lambda, SQS), Docker, Kubernetes, GitHub Actions",
    must_haves=["scalability|scalable", "reliability|reliable", "testing", "observability|monitoring",
                "pipeline", "architecture|system design", "product"],
)
P[2] = dict(  # Boeing  Software Engineer (aircraft/ground real-time, agile, testing)
    summary="Software Engineer at Amazon Prime Video building and integrating distributed backend software for systems serving 1M+ users, experienced in agile development, architecture and interface design, unit and integration testing, and analytical problem-solving across the software lifecycle.",
    top_bullets=[
        "Developed and integrated backend software components into distributed AI systems on agile teams, performing unit and integration testing and peer reviews to ensure reliability.",
        "Resolved complex production issues with analytical debugging across distributed service boundaries, parallelizing downstream calls to improve P99 latency 3x under peak load.",
    ],
    technical_skills="Languages: Python, Java, C++, Kotlin, SQL\nPractices: Agile, Software Architecture, Unit/Integration Testing, Code Review, Interface Design\nSystems: Distributed Systems, REST APIs, Multithreading, gRPC, Linux/Unix, Fault Tolerance\nObservability: CloudWatch, Monitoring, Distributed Tracing, Performance Profiling\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, Git",
    must_haves=["agile", "testing|integration testing", "architecture", "distributed systems",
                "debugging|troubleshoot", "interface|api", "software development|develop"],
)
P[3] = dict(  # Trimble  .NET/Kafka/SQL Server/Docker/K8s/Azure/CI/CD (candidate lacks .NET/C#)
    summary="Software Engineer at Amazon Prime Video building event-driven, distributed backend services and CI/CD pipelines for systems serving 1M+ users, skilled in microservices, SQL, Docker, Kubernetes, GitHub Actions, and end-to-end production debugging on cloud infrastructure.",
    top_bullets=[
        "Built and operated distributed microservices with Docker, Kubernetes, and GitHub Actions CI/CD, diagnosing production issues end-to-end from service logs down to the SQL database.",
        "Developed event-driven data integrations across services and parallelized downstream calls, improving P99 latency 3x while collaborating with product, QA, and DevOps teams.",
    ],
    technical_skills="Languages: Python, Java, C++, SQL, Kotlin\nBackend: Microservices, Event-Driven Integration, REST APIs, gRPC, Distributed Systems\nData: SQL, PostgreSQL, NoSQL, Kafka, Airflow, Spark\nCI/CD and DevOps: Docker, Kubernetes, GitHub Actions, Git, CI/CD\nCloud and Observability: AWS, Azure, CloudWatch, Monitoring, Distributed Tracing",
    must_haves=["microservices", "kafka|event-driven", "sql", "docker", "kubernetes",
                "ci cd|pipeline", "cloud|azure|aws", "agile|scrum", "dotnet|.net|c#"],
)
P[4] = dict(  # Cisco  Devices Tech Group (C/C++, Python, Git, debugging, Java)
    summary="Software Engineer at Amazon Prime Video building distributed backend services serving 1M+ users, proficient in C++ and Python with strong debugging, version control, and command-line workflows, writing clean, maintainable, efficient code to established standards.",
    top_bullets=[
        "Developed and debugged backend services in Python and C++ for 1M+ users, resolving software defects and performance issues with Git-based version control and clean coding standards.",
        "Automated regression testing and CI/CD workflows that triaged build failures and cut pre-production defects 30%, improving efficiency across the development lifecycle.",
    ],
    technical_skills="Languages: C, C++, Python, Java, SQL, Bash\nPractices: Version Control (Git), Debugging, Automation, Clean Code, Code Review\nSystems: Distributed Systems, REST APIs, Multithreading, Linux/Unix\nCI/CD and DevOps: GitHub Actions, Docker, Kubernetes, CI/CD\nCloud and Observability: AWS, CloudWatch, Monitoring, Performance Profiling",
    must_haves=["c++|cpp", "python", "git|version control", "debugging|troubleshooting",
                "automation|scripting", "java", "clean code|maintainable"],
)
P[5] = dict(  # Google  SWE (GenAI prototyping, ML pipelines, testing, deployment lifecycle)
    summary="Software Engineer at Amazon Prime Video prototyping GenAI solutions and building ML pipelines for distributed systems serving 1M+ users, with strong testing, debugging, and full deployment-lifecycle ownership including monitoring, automation, and reliability.",
    top_bullets=[
        "Prototyped GenAI solutions and built ML evaluation pipelines processing 50K+ conversations daily with LLM-as-judge, increasing defect discovery 60% with actionable triage insights.",
        "Managed the full deployment lifecycle with comprehensive integration, performance, and security testing plus CloudWatch monitoring and automation, improving long-term scalability.",
    ],
    technical_skills="Languages: Python, Java, C++, JavaScript, SQL\nAI/ML: GenAI, LLM Integration, ML Pipelines, Model Evaluation, RAG, Datasets\nPractices: Integration/Performance Testing, Debugging, Code Review, Root-Cause Analysis\nSystems: Distributed Systems, REST APIs, Multithreading, gRPC, Linux\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, CloudWatch, Monitoring",
    must_haves=["genai|generative", "ml pipeline|pipelines", "testing", "debugging|root cause",
                "deployment|lifecycle", "monitoring|observability", "python", "scalability|scalable"],
)
P[6] = dict(  # Thomson Reuters  AI Engineer (Python/TS, AI coding, GenAI, agents, vector DB, AWS)
    summary="Software Engineer at Amazon Prime Video building GenAI products and LLM-powered systems for distributed services serving 1M+ users, skilled in Python, AI-augmented development, agent architectures, vector search, and AWS, shipping reliable AI features end-to-end.",
    top_bullets=[
        "Built LLM-powered evaluation and retrieval systems processing 50K+ conversations daily with vector search and embeddings, increasing defect discovery 60% with actionable insights.",
        "Shipped 10+ GenAI features from prototype to production using agent-based pipelines on AWS, leveraging AI-augmented coding tools to accelerate delivery and improve quality 25%.",
    ],
    technical_skills="Languages: Python, JavaScript/TypeScript, SQL, Java\nAI/ML: GenAI, LLM Integration, Agent Architectures, RAG, Embeddings, Vector Search, LangChain\nAI Tooling: AI-Augmented Coding (Copilot/Claude Code), Prompt Engineering\nBackend: REST APIs, FastAPI, PostgreSQL, Distributed Systems\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, GitHub Actions",
    must_haves=["python", "generative|genai|llm", "agent|agentic", "vector|embeddings",
                "aws", "typescript|javascript", "search|retrieval"],
)
P[7] = dict(  # Cubic  Associate SWE (C/C++/python/JS, UNIX/Linux, Git, testing, agile)
    summary="Software Engineer at Amazon Prime Video building and testing high-quality distributed software for systems serving 1M+ users, skilled in Python, C++, and JavaScript with Linux, Git version control, unit testing, and agile collaboration on complex problems.",
    top_bullets=[
        "Designed and tested high-quality backend software in Python and C++ following best practices, keeping code well-structured, unit-tested, and maintainable across the codebase.",
        "Collaborated within an agile team using Git and Linux to resolve defects, parallelizing downstream calls and improving P99 latency 3x under peak production load.",
    ],
    technical_skills="Languages: Python, C, C++, JavaScript, SQL\nPractices: Unit Testing, Agile, Code Review, Version Control (Git), Clean Code\nSystems: Distributed Systems, REST APIs, UNIX/Linux, Multithreading, Fault Tolerance\nCI/CD and DevOps: GitHub Actions, Docker, Kubernetes, CI/CD\nCloud and Observability: AWS, CloudWatch, Monitoring, Performance Profiling",
    must_haves=["python|c++|javascript", "unix|linux", "git|version control", "testing|unit tested",
                "agile", "problem-solving|analytical", "software development|develop"],
)
P[8] = dict(  # Northrop Grumman  SWE DevOps (C++/C#/Java/Python, CI/CD tooling, Docker/K8s, agile)
    summary="Software Engineer at Amazon Prime Video owning CI/CD build and delivery pipelines for distributed systems serving 1M+ users, skilled in Python and C++, agile delivery, and DevOps tooling including GitHub, Docker, and Kubernetes for mission-critical software.",
    top_bullets=[
        "Owned and automated CI/CD build and delivery pipelines with GitHub Actions, Docker, and Kubernetes, triaging build failures and cutting pre-production defects 30%.",
        "Developed mission-critical software in Python and C++ on agile teams, coordinating builds and delivery schedules with stakeholders to simplify the release process.",
    ],
    technical_skills="Languages: C++, Java, Python, SQL, Bash\nCI/CD and DevOps: GitHub Actions, GitLab, Docker, Kubernetes, Jenkins, CI/CD, Change Management\nPractices: Agile, Build/Delivery Automation, Code Review, Configuration Management\nSystems: Distributed Systems, REST APIs, Linux/Unix, Multithreading\nCloud and Observability: AWS, CloudWatch, Monitoring, Distributed Tracing",
    must_haves=["c++|python", "ci cd|cicd|pipeline", "docker", "kubernetes", "agile",
                "github|gitlab|jenkins", "build|delivery", "automation|automate"],
)
P[9] = dict(  # MTA  Application Developer 3 (Data and AI Engineering; code, test, docs, design)
    summary="Software Engineer at Amazon Prime Video coding and delivering maintainable distributed applications and data/AI pipelines for systems serving 1M+ users, with strong testing, debugging, documentation, and system design across business and AI engineering requirements.",
    top_bullets=[
        "Coded and delivered maintainable backend applications and AI data pipelines for 1M+ users, developing functional test plans and technical documentation to high-quality standards.",
        "Investigated and resolved production problems across distributed systems through debugging and observability, cutting pre-production defects 30% via CI/CD and regression testing.",
    ],
    technical_skills="Languages: Python, Java, JavaScript, SQL, Bash\nData and AI: ETL Pipelines, Spark, Airflow, LLM Integration, Data Modeling\nPractices: System Design, Testing, Documentation, Debugging, Agile\nSystems: Distributed Systems, REST APIs, PostgreSQL, NoSQL, Linux\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, CloudWatch",
    must_haves=["software|code", "testing|test plans", "documentation", "debugging|production problems",
                "data|ai", "system design|design", "sql", "maintainable"],
)
P[10] = dict(  # Slingshot AI  AI Native SWE (thin form; AI-native eng, build things)
    summary="Software Engineer at Amazon Prime Video building AI-native, LLM-powered backend systems for distributed services serving 1M+ users, combining strong software fundamentals with generative AI, retrieval, and evaluation to ship high-impact features fast.",
    top_bullets=[
        "Built AI-native systems including an LLM-as-judge evaluation framework processing 50K+ conversations daily, increasing defect discovery 60% with actionable triage insights.",
        "Shipped 10+ AI features from prototype to production with feature gating and A/B testing, leveraging generative AI tools to accelerate development and improve quality 25%.",
    ],
    technical_skills="Languages: Python, JavaScript/TypeScript, Java, C++, SQL\nAI/ML: LLM Integration, GenAI, RAG, Embeddings, Vector Search, LangChain, Prompt Engineering\nPractices: Rapid Prototyping, A/B Testing, Feature Gating, CI/CD\nSystems: Distributed Systems, REST APIs, Multithreading, Linux\nCloud and DevOps: AWS, Docker, Kubernetes, CloudWatch",
    must_haves=["python", "ai|llm", "generative|genai", "retrieval|vector|embeddings",
                "build|ship", "distributed systems", "experimentation|a/b|prototyping"],
)
P[11] = dict(  # Leidos  Entry SWE (C#/Java/JS/TS/Python/shell, gitlab, DevOps, agile, Jira)
    summary="Software Engineer at Amazon Prime Video building and integrating distributed web and backend software for systems serving 1M+ users, skilled in Java, JavaScript/TypeScript, Python, shell scripting, Git-based version control, and agile DevOps delivery.",
    top_bullets=[
        "Developed and integrated backend and web-application features in Java, JavaScript, and Python, documenting functionality in version-controlled repositories using DevOps tools and CI/CD.",
        "Collaborated on an agile team using Jira to assess tickets, write tests, and deliver features against acceptance criteria, cutting pre-production defects 30%.",
    ],
    technical_skills="Languages: Java, JavaScript/TypeScript, Python, C++, Shell Scripting, SQL\nPractices: Agile, DevOps, Version Control (Git/GitLab), Testing, Jira/Confluence\nSystems: Distributed Systems, REST APIs, Web Applications, Linux/Unix\nCI/CD and DevOps: GitHub Actions, GitLab CI, Docker, Kubernetes, CI/CD\nCloud and Observability: AWS, CloudWatch, Monitoring",
    must_haves=["java|python|javascript", "shell scripting|bash", "version control|git|gitlab",
                "agile", "devops|ci cd", "testing", "web application|web"],
)
P[12] = dict(  # HP  Diagnostics & Applications SWE (systems software, integrate APIs/DBs, test plans, SRE-ish)
    summary="Software Engineer at Amazon Prime Video developing and integrating distributed systems software for services serving 1M+ users, skilled in building modules, integrating APIs and databases, executing test plans, debugging, and improving the full service lifecycle.",
    top_bullets=[
        "Developed software modules and integrated services with databases, APIs, and third-party systems for 1M+ users, ensuring seamless data flow and reliable functionality.",
        "Executed test plans and debugged issues across the service lifecycle with CloudWatch monitoring, improving design, deployment, and operation while cutting defects 30%.",
    ],
    technical_skills="Languages: Python, Java, C++, JavaScript, SQL, Bash\nSystems: Distributed Systems, REST APIs, Databases, Third-Party Integration, Linux/Unix\nPractices: Test Plans, Debugging, System Design, Requirements Analysis, Code Review\nObservability: CloudWatch, Monitoring, Distributed Tracing, Performance Profiling\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD",
    must_haves=["software|develop", "integration|integrate", "api", "database|databases",
                "testing|test plans", "debugging|debug", "deployment|operation", "linux|operating systems"],
)
P[13] = dict(  # Bot Auto  SWE Operation Platforms (backend/frontend, APIs, DBs, event-driven, reliability)
    summary="Software Engineer at Amazon Prime Video building backend services and operator tools for distributed platforms serving 1M+ users, skilled in APIs, databases, event-driven integrations, and improving production reliability with clean, well-documented code.",
    top_bullets=[
        "Built backend services and APIs with event-driven integrations and databases for 1M+ users, implementing core workflows with attention to usability and reliability.",
        "Improved production performance and reliability by debugging across distributed boundaries and parallelizing downstream calls, cutting P99 latency 3x under peak load.",
    ],
    technical_skills="Languages: Python, Java, JavaScript, C++, SQL\nBackend: REST APIs, Event-Driven Integration, Databases, Microservices, Distributed Systems\nData: PostgreSQL, NoSQL, Kafka, Airflow\nPractices: Testing, Debugging, Clean Code, Agile, Code Review\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, CloudWatch",
    must_haves=["backend|services", "api|apis", "database|databases", "event-driven|kafka",
                "reliability|performance", "debugging|testing", "python|java", "distributed systems"],
)
P[14] = dict(  # RTX  Core Systems & Libraries (C++, requirements, test cases, revision control)
    summary="Software Engineer at Amazon Prime Video building distributed core backend systems and libraries for services serving 1M+ users, skilled in C++ development, requirements and test-case authoring, automated testing, and Git-based revision control.",
    top_bullets=[
        "Developed core backend systems and libraries in C++ for 1M+ users, authoring requirements and test cases with automated test procedures to ensure reliability.",
        "Automated regression testing and revision-controlled CI/CD workflows in Git, triaging build failures and cutting pre-production defects 30% across release cycles.",
    ],
    technical_skills="Languages: C++, Python, Java, SQL, Bash\nPractices: Requirements, Test Cases, Automated Testing, Revision Control (Git), Code Review\nSystems: Distributed Systems, Core Libraries, REST APIs, Multithreading, Linux/Unix\nCI/CD and DevOps: GitHub Actions, Docker, Kubernetes, CI/CD\nCloud and Observability: AWS, CloudWatch, Monitoring",
    must_haves=["c++|cpp", "requirements", "test cases|testing", "automated test|automation",
                "revision control|git", "systems|libraries", "debugging|defects"],
)
P[15] = dict(  # Torc Robotics  SWE Mission Control (web apps, backend, workflows, distributed)
    summary="Software Engineer at Amazon Prime Video building web-based and backend applications for distributed systems serving 1M+ users, creating reliable workflows, APIs, and observability that give teams visibility into critical operations end-to-end.",
    top_bullets=[
        "Built web-based backend applications and APIs supporting critical operational workflows for 1M+ users, designing for usability, visibility, and reliable end-to-end execution.",
        "Implemented CloudWatch observability dashboards giving real-time visibility into pipeline and service health across distributed systems, surfacing regressions and failures early.",
    ],
    technical_skills="Languages: Python, JavaScript/TypeScript, Java, SQL\nFrontend/Web: React, REST APIs, Web Applications\nBackend: Distributed Systems, Microservices, gRPC, PostgreSQL, NoSQL\nObservability: CloudWatch, Monitoring, Distributed Tracing, Performance Profiling\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD",
    must_haves=["web|web application", "backend|services", "api|apis", "workflow|workflows",
                "distributed systems", "reliability|monitoring", "python|javascript"],
)
P[16] = dict(  # Autodesk  Graduate SWE (full SDLC, C++/Python/TS/React, GitHub/Jenkins, agile, unit tests)
    summary="Software Engineer at Amazon Prime Video building distributed software across the full development lifecycle for systems serving 1M+ users, skilled in C++, Python, and TypeScript/React with agile Scrum, GitHub CI, and unit testing.",
    top_bullets=[
        "Developed clean, reliable code across the full software lifecycle in Python, C++, and TypeScript within agile Scrum teams, maintaining unit tests and engineering standards.",
        "Used GitHub Actions source control and continuous integration to deliver features and code reviews, triaging build failures and cutting pre-production defects 30%.",
    ],
    technical_skills="Languages: C++, Python, TypeScript/React, Java, SQL\nPractices: Agile Scrum, Unit Testing, Code Review, Source Control, Continuous Integration\nSystems: Distributed Systems, REST APIs, Desktop/Web Applications, Linux\nCI/CD and DevOps: GitHub Actions, Jenkins, Docker, Kubernetes, CI/CD\nCloud and Observability: AWS, CloudWatch, Monitoring",
    must_haves=["c++|python|typescript", "agile|scrum", "unit test|testing", "code review",
                "source control|github|git", "continuous integration|ci", "react|web"],
)
P[17] = dict(  # Asana  SWE Early Career Product (end-to-end, data models, product dev)
    summary="Software Engineer at Amazon Prime Video building product features end-to-end for distributed systems serving 1M+ users, from data models to interaction behavior, partnering with design and product through the full development lifecycle.",
    top_bullets=[
        "Built product features end-to-end for 1M+ users, from designing data models to implementing interaction behavior, partnering closely with design and product teams.",
        "Drove continuous improvement across the product lifecycle with CI/CD, regression testing, and CloudWatch observability, cutting pre-production defects 30% in distributed systems.",
    ],
    technical_skills="Languages: Python, JavaScript/TypeScript, Java, SQL\nPractices: Product Development, Data Modeling, System Design, Testing, Code Review, Agile\nSystems: Distributed Systems, REST APIs, Microservices, PostgreSQL, NoSQL\nObservability: CloudWatch, Monitoring, Distributed Tracing\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD",
    must_haves=["product", "end-to-end|data model", "feature|features", "testing",
                "distributed systems", "design", "python|javascript"],
)
P[18] = dict(  # Cadence  Agentic AI Engineer (deep learning, transformers, LLM, RAG, agents, vector DB, PyTorch/HF)
    summary="Software Engineer at Amazon Prime Video building LLM-powered, agentic AI systems for distributed services serving 1M+ users, with hands-on RAG, retrieval, vector search, and LLM evaluation, writing clean, tested, version-controlled Python.",
    top_bullets=[
        "Built agentic LLM systems and RAG retrieval pipelines with vector search and embeddings, processing 50K+ conversations daily and increasing defect discovery 60%.",
        "Shipped 10+ LLM features from prototype to production with feature gating and A/B evaluation, writing clean, tested, version-controlled Python across the stack.",
    ],
    technical_skills="Languages: Python, C++, SQL, JavaScript\nAI/ML: LLMs, Transformers, RAG, Retrieval, Vector Search, Embeddings, LLM Evaluation, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, Hugging Face, LangChain, FAISS, OpenSearch\nAgentic AI: Agent Frameworks, Tool-Calling, Prompt Engineering, Structured Output\nSystems and Cloud: Distributed Systems, REST APIs, AWS, Docker, Kubernetes, CI/CD",
    must_haves=["llm|transformers", "rag|retrieval", "vector|embeddings", "agent|agentic",
                "python", "pytorch|hugging face", "fine-tuning|evaluation"],
)
P[19] = dict(  # Pinterest  SWE 1 Backend (large-scale distributed, A/B, prototyping, end-to-end)
    summary="Software Engineer at Amazon Prime Video designing and operating large-scale distributed backend systems serving 1M+ users, building Pinner-style features end-to-end with rapid prototyping, A/B testing, and scalable, high-quality architecture.",
    top_bullets=[
        "Designed and operated large-scale distributed backend systems for 1M+ users, building features end-to-end from prototyping and A/B tests to scalable production architecture.",
        "Parallelized downstream service calls and tuned distributed systems to improve P99 latency 3x under peak load, partnering with product and design teams.",
    ],
    technical_skills="Languages: Python, Java, C++, SQL\nBackend: Distributed Systems, Microservices, REST APIs, gRPC, Scalability, Fault Tolerance\nPractices: A/B Testing, Rapid Prototyping, System Design, Automated Testing, Code Review\nData: PostgreSQL, NoSQL, Kafka, Airflow\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD, CloudWatch",
    must_haves=["backend", "distributed systems|large scale", "scalable|scale", "a/b|experimentation|prototyping",
                "api|apis", "end-to-end", "python|java"],
)

# ---- 20 ML patches (indices 20-39) ----------------------------------------- #
P[20] = dict(  # EXL  Data Scientist Associate (data analysis, preprocessing, stats, model dev)
    summary="Machine Learning Engineer at Amazon Prime Video building production data and model pipelines for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in Python, statistical analysis, data preprocessing, and model development and evaluation.",
    top_bullets=[
        "Developed model and data pipelines with preprocessing, statistical analysis, and evaluation in Python, increasing defect discovery 60% through rigorous offline and online validation.",
        "Built data-cleaning and feature-engineering workflows over large datasets, documenting data science processes and collaborating with senior scientists to deliver actionable insights.",
    ],
    technical_skills="Languages: Python, SQL, R-style Statistical Analysis\nData Science: Data Preprocessing, Statistical Analysis, Feature Engineering, Data Visualization, Model Evaluation\nML: scikit-learn, PyTorch, NLP, Model Development, XGBoost\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL\nCloud: AWS, Azure (Databricks)",
    must_haves=["python", "data analysis|statistical", "preprocessing|data cleaning",
                "model development|model", "visualization|data visualization", "feature engineering"],
)
P[21] = dict(  # Waymark  Senior Data Scientist (AI/ML models, LLM tools, multi-agent, Python pipelines)
    summary="Machine Learning Engineer at Amazon Prime Video leading development and deployment of production ML and LLM systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in predictive modeling, multi-agent LLM tools, and Python data pipelines.",
    top_bullets=[
        "Led development and deployment of production ML prediction models and LLM-based multi-agent tools serving 1M+ users, lifting CTR 16% through iterative offline and online evaluation.",
        "Built and optimized Python data pipelines and an LLM-as-judge evaluation framework over 50K+ conversations daily, increasing defect discovery 60% with actionable insights.",
    ],
    technical_skills="Languages: Python, SQL, Kotlin\nML/AI: Prediction Models, LLMs, Multi-Agent Systems, Model Evaluation, NLP, RAG, Ranking\nFrameworks: PyTorch, TensorFlow, scikit-learn, LangChain, FAISS\nData: Pandas, NumPy, Spark, Kafka, Airflow, PostgreSQL\nSystems and Cloud: Distributed Systems, REST APIs, AWS, Docker, Kubernetes",
    must_haves=["ml|machine learning", "prediction|prediction models", "llm", "multi-agent|agent",
                "python", "data pipeline|pipelines", "deployment|deploy", "evaluation"],
)
P[22] = dict(  # Pigment  AI Deployment Strategist (thin form; deploy AI for clients, technical+consulting)
    summary="Machine Learning Engineer at Amazon Prime Video deploying production LLM and AI systems for distributed services serving 1M+ users; first-author EMNLP 2025 researcher who partners cross-functionally to take AI solutions from prototype to production.",
    top_bullets=[
        "Deployed 10+ production AI and LLM features from prototype to production with feature gating and A/B evaluation, partnering cross-functionally across product, science, and engineering.",
        "Built an LLM-as-judge evaluation framework over 50K+ conversations daily, increasing defect discovery 60% and translating ambiguous needs into reliable deployed AI systems.",
    ],
    technical_skills="Languages: Python, SQL, Kotlin\nAI/ML: LLM Integration, GenAI, RAG, Model Evaluation, Prompt Engineering, Deployment\nFrameworks: PyTorch, LangChain, FAISS, OpenSearch\nPractices: A/B Testing, Feature Gating, Cross-Functional Delivery, Stakeholder Collaboration\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems, REST APIs",
    must_haves=["ai|llm", "deployment|deploy", "production", "cross-functional|stakeholder",
                "python", "evaluation|a/b", "prototype"],
)
P[23] = dict(  # Northeastern  MLE AI Solutions Hub (Python, ML deployment/serving, LLM/agentic, prompt eng)
    summary="Machine Learning Engineer at Amazon Prime Video building, deploying, and serving production ML and LLM systems for services serving 1M+ users; first-author EMNLP 2025 researcher skilled in model serving, agentic AI, and structured prompting for reliable pipelines.",
    top_bullets=[
        "Deployed and served production ML and LLM systems for 1M+ users with model packaging, validation, and inference, lifting CTR 16% via iterative offline and online evaluation.",
        "Built agentic LLM pipelines with tool use, structured output, and an LLM-as-judge evaluation framework over 50K+ conversations daily, increasing defect discovery 60%.",
    ],
    technical_skills="Languages: Python, SQL, C++\nML Engineering: Model Packaging, Serving, Inference, Validation, Model Evaluation, Deep Learning\nLLM/Agentic: LLMs, RAG, Agentic AI, Tool Use, Structured Output, Prompt Engineering, LangChain\nFrameworks: PyTorch, TensorFlow, FAISS, OpenSearch\nSystems and Cloud: Distributed Systems, REST APIs, AWS, Docker, Kubernetes, CI/CD",
    must_haves=["python", "ml|machine learning", "serving|inference|deployment", "llm",
                "agentic|agent", "prompt|structured output", "deep learning|generative", "evaluation"],
)
P[24] = dict(  # Truist  Data Scientist 1 Card Fraud (ML, NN, NLP, Python, data viz, end-to-end)
    summary="Machine Learning Engineer at Amazon Prime Video building production ML, neural-network, and NLP systems for services serving 1M+ users; first-author EMNLP 2025 researcher delivering end-to-end data science with Python and rigorous evaluation.",
    top_bullets=[
        "Built production machine-learning, neural-network, and NLP models in Python over structured and unstructured data, lifting CTR 16% through iterative offline and online evaluation.",
        "Owned end-to-end data science delivery from problem scoping to deployment, building an LLM-as-judge evaluation framework that increased defect discovery 60% for stakeholders.",
    ],
    technical_skills="Languages: Python, SQL\nML/AI: Machine Learning, Neural Networks, NLP, Model Evaluation, Feature Engineering, XGBoost\nFrameworks: PyTorch, TensorFlow, scikit-learn, LangChain\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL, Data Visualization\nCloud and Systems: AWS, Azure, Distributed Systems, REST APIs",
    must_haves=["machine learning|ml", "neural network|neural", "nlp", "python",
                "data visualization|visualization", "end-to-end|deploy", "evaluation|analytics"],
)
P[25] = dict(  # USAA  Data Scientist 1 (define business problems, complex analysis, ML)
    summary="Machine Learning Engineer at Amazon Prime Video building production ML and analytics systems for services serving 1M+ users; first-author EMNLP 2025 researcher who scopes business problems and delivers complex data science with Python and SQL.",
    top_bullets=[
        "Built ML models and complex analyses over large datasets in Python and SQL for 1M+ users, lifting CTR 16% through iterative offline and online evaluation.",
        "Partnered cross-functionally to define business problems and research questions, delivering an LLM-as-judge evaluation framework that increased defect discovery 60%.",
    ],
    technical_skills="Languages: Python, SQL\nML/AI: Machine Learning, Model Evaluation, NLP, Feature Engineering, XGBoost, Statistical Analysis\nFrameworks: PyTorch, TensorFlow, scikit-learn\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL, Data Visualization\nCloud and Systems: AWS, Azure, Distributed Systems, REST APIs",
    must_haves=["machine learning|ml", "python", "sql", "data analysis|analytics|complex",
                "model|modeling", "cross-functional|stakeholder", "research"],
)
P[26] = dict(  # KLA  Algorithm Engineer Deep Learning (SOTA DL, GenAI, CV, model training/optimization)
    summary="Machine Learning Engineer at Amazon Prime Video building production deep-learning and GenAI models for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in model design, training, evaluation, and inference optimization on real datasets.",
    top_bullets=[
        "Designed and trained deep-learning and GenAI models on domain datasets, evaluating and validating performance against defined metrics and lifting CTR 16% via iterative evaluation.",
        "Optimized model architectures and inference throughput with retrieval and ranking pipelines (FAISS + NDCG), serving 1M+ users at 0.5s end-to-end latency.",
    ],
    technical_skills="Languages: Python, C++, SQL\nDeep Learning: Deep Learning, GenAI, Model Architectures, Training, Fine-tuning (LoRA/PEFT), Model Compression\nFrameworks: PyTorch, TensorFlow, Hugging Face, FAISS\nML Systems: Ranking, Retrieval, Embeddings, Model Evaluation, Inference Optimization\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems",
    must_haves=["deep learning", "genai|generative", "model training|training", "model|architectures",
                "python", "evaluation|validate", "inference|optimization", "pytorch"],
)
P[27] = dict(  # ByteDance  AI Vision Research Engineer PhD (VR/AR, vision, research)
    summary="Machine Learning Engineer at Amazon Prime Video building production deep-learning, vision, and LLM systems for services serving 1M+ users; first-author EMNLP 2025 researcher experienced in model research, training, and evaluation at consumer scale.",
    top_bullets=[
        "Built production deep-learning retrieval and ranking models (FAISS + NDCG) serving 1M+ users at 0.5s latency, lifting CTR 16% via iterative offline and online evaluation.",
        "Researched and trained multimodal LLM evaluation models over 50K+ conversations daily with LLM-as-judge, increasing defect discovery 60% and publishing first-author EMNLP work.",
    ],
    technical_skills="Languages: Python, C++, SQL\nDeep Learning: Deep Learning, Computer Vision, Multimodal Models, Model Training, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, TensorFlow, Hugging Face, FAISS\nResearch: First-Author EMNLP 2025, Model Evaluation, Retrieval, Ranking\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems",
    must_haves=["deep learning", "vision|multimodal", "research|publication", "model training|training",
                "python", "evaluation", "pytorch"],
)
P[28] = dict(  # Primetals  Data Science Associate Governance (analytics, Python, Power BI, GenAI, automation)
    summary="Machine Learning Engineer at Amazon Prime Video building production analytics, automation, and GenAI-enabled systems for services serving 1M+ users; first-author EMNLP 2025 researcher skilled in Python analytics, data-driven testing, and scalable, repeatable pipelines.",
    top_bullets=[
        "Built repeatable, scalable Python analytics routines and GenAI-enabled automation that expanded testing coverage and surfaced data-driven insights for governance and assurance.",
        "Designed an LLM-as-judge evaluation framework over 50K+ conversations daily with automated validation, increasing defect discovery 60% with traceable, defensible analytics.",
    ],
    technical_skills="Languages: Python, SQL\nAnalytics: Data Analytics, Automation, Data Visualization, GenAI Applications, Statistical Analysis\nML/AI: LLM Integration, Model Evaluation, NLP, RAG\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL\nCloud: AWS, Azure (Databricks)",
    must_haves=["python", "analytics|data analytics", "automation|automate", "genai|generative",
                "data visualization|dashboard", "evaluation|testing"],
)
P[29] = dict(  # Cisco  AI Researcher PhD (LLM infra, training/inference/optimization, vLLM, agents)
    summary="Machine Learning Engineer at Amazon Prime Video building production LLM systems and evaluation infrastructure for services serving 1M+ users; first-author EMNLP 2025 researcher with hands-on LLM training, inference, optimization, and agent frameworks in Python.",
    top_bullets=[
        "Built LLM training, inference, and evaluation infrastructure in Python over 50K+ conversations daily with LLM-as-judge, increasing defect discovery 60% with actionable insights.",
        "Optimized retrieval and ranking pipelines (FAISS + NDCG) and parallelized inference for 1M+ users at 0.5s latency, lifting CTR 16% through iterative evaluation.",
    ],
    technical_skills="Languages: Python, C++, SQL\nLLM/AI: LLMs, Training, Inference, Optimization, RAG, Agent Frameworks, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, Hugging Face, FAISS, OpenSearch, LangChain\nResearch: First-Author EMNLP 2025, Model Evaluation, Distributed Systems\nCloud and Systems: AWS, Docker, Kubernetes, Async Programming",
    must_haves=["llm", "training|inference", "optimization|optimize", "python",
                "agent|agentic|framework", "research|publication", "distributed systems"],
)
P[30] = dict(  # Elsevier  Data Scientist (ML/NLP, RAG, transformers, GenAI, production Python)
    summary="Machine Learning Engineer at Amazon Prime Video building production NLP, RAG, and GenAI pipelines for services serving 1M+ users; first-author EMNLP 2025 researcher writing production-ready Python for model inference, retrieval, and evaluation.",
    top_bullets=[
        "Built and optimized RAG and NLP pipelines with transformer models and retrieval over embeddings, writing production-ready Python modules for inference and evaluation.",
        "Developed an LLM-as-judge evaluation framework over 50K+ conversations daily with automated validation, increasing defect discovery 60% and monitoring model performance over time.",
    ],
    technical_skills="Languages: Python, SQL\nML/NLP: NLP, RAG, Transformers, GenAI, Embeddings, Model Evaluation, Inference Pipelines\nFrameworks: PyTorch, TensorFlow, Hugging Face, LangChain, FAISS, OpenSearch\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems",
    must_haves=["nlp", "rag|retrieval", "transformer|transformers", "genai|generative",
                "python", "embeddings|inference", "evaluation", "production"],
)
P[31] = dict(  # Wellmark  Data Science Associate (discovery, data gathering, models, reporting)
    summary="Machine Learning Engineer at Amazon Prime Video building production models and analytics for services serving 1M+ users; first-author EMNLP 2025 researcher skilled in Python and SQL who scopes business problems and conveys findings to stakeholders.",
    top_bullets=[
        "Built and executed models over sourced data in Python and SQL to analyze business outcomes, lifting engagement 30% and summarizing findings for stakeholders.",
        "Profiled and prepared large datasets, developing an LLM-as-judge evaluation framework that increased defect discovery 60% while managing multiple projects to deadline.",
    ],
    technical_skills="Languages: Python, SQL\nData Science: Data Profiling, Modeling, Statistical Analysis, Forecasting, Data Visualization, Reporting\nML/AI: Machine Learning, Model Evaluation, NLP, XGBoost\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL\nCloud: AWS, Azure (Databricks)",
    must_haves=["python", "sql", "model|models", "data|datasets", "visualization|reporting",
                "stakeholder|business", "forecasting|analysis"],
)
P[32] = dict(  # ByteDance  Graduate AIOps Engineer Data Center Networking (LLM + networking + observability)
    summary="Machine Learning Engineer at Amazon Prime Video building LLM-powered observability and automation for distributed systems serving 1M+ users; first-author EMNLP 2025 researcher combining LLM development with monitoring and pipeline reliability at scale.",
    top_bullets=[
        "Built LLM-powered observability and automation over distributed systems, implementing CloudWatch dashboards for real-time detection of pipeline regressions and service failures.",
        "Designed an LLM-as-judge evaluation framework over 50K+ conversations daily with automated validation, increasing defect discovery 60% and transforming reactive operations.",
    ],
    technical_skills="Languages: Python, C++, SQL, Bash\nAI/ML: LLM Integration, GenAI, Model Evaluation, RAG, Anomaly Detection\nObservability: CloudWatch, Monitoring, Distributed Tracing, AIOps, Performance Profiling\nSystems: Distributed Systems, Networking, REST APIs, Linux/Unix\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD",
    must_haves=["llm", "observability|monitoring", "automation|aiops", "distributed systems",
                "python", "networking|network", "evaluation|detection"],
)
P[33] = dict(  # ByteDance  Grad MLE E-Commerce Governance CV/NLP/Multimodal/LLM
    summary="Machine Learning Engineer at Amazon Prime Video building production CV, NLP, and LLM models for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in ranking, retrieval, and multimodal model development at consumer scale.",
    top_bullets=[
        "Built production NLP, multimodal, and LLM models with retrieval and ranking pipelines (FAISS + NDCG) serving 1M+ users at 0.5s latency, lifting CTR 16%.",
        "Designed an LLM-as-judge evaluation framework over 50K+ conversations daily to identify low-quality and risk content, increasing defect discovery 60% with actionable insights.",
    ],
    technical_skills="Languages: Python, C++, SQL\nML/AI: NLP, Multimodal Models, LLMs, Computer Vision, Ranking, Retrieval, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, TensorFlow, Hugging Face, FAISS, OpenSearch\nResearch: First-Author EMNLP 2025, Model Evaluation, Embeddings\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems",
    must_haves=["nlp", "multimodal|vision", "llm", "ranking|retrieval", "python",
                "model|models", "evaluation", "pytorch"],
)
P[34] = dict(  # ByteDance  Grad MLE E-Commerce Governance PhD (GNN, MOO, time-series, LLM)
    summary="Machine Learning Engineer at Amazon Prime Video building production LLM, ranking, and time-series models for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in retrieval, evaluation, and large-scale model development.",
    top_bullets=[
        "Built production LLM, ranking, and retrieval models (FAISS + NDCG) serving 1M+ users at 0.5s latency, lifting CTR 16% via iterative offline and online evaluation.",
        "Developed time-series and forecasting models on TB-scale data with XGBoost, cutting supply-chain costs $4M, and an LLM-as-judge framework increasing defect discovery 60%.",
    ],
    technical_skills="Languages: Python, C++, SQL\nML/AI: LLMs, Ranking, Retrieval, Time-Series, Forecasting, Multi-Objective Optimization, Model Evaluation\nFrameworks: PyTorch, TensorFlow, XGBoost, Hugging Face, FAISS\nResearch: First-Author EMNLP 2025, Embeddings, Fine-tuning (LoRA/PEFT)\nCloud and Systems: AWS, Spark, Docker, Kubernetes, Distributed Systems",
    must_haves=["llm", "ranking|retrieval", "time series|time-series|forecasting", "optimization",
                "python", "model|models", "evaluation", "pytorch|xgboost"],
)
P[35] = dict(  # ByteDance  Graduate MLE (general governance, algorithms for risk)
    summary="Machine Learning Engineer at Amazon Prime Video building production ranking, retrieval, and LLM models for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in model development, evaluation, and large-scale ML at consumer scale.",
    top_bullets=[
        "Built production ranking and retrieval models (FAISS + NDCG) serving 1M+ users at 0.5s latency, lifting CTR 16% via iterative offline and online evaluation.",
        "Designed an LLM-as-judge evaluation framework over 50K+ conversations daily with automated validation to flag low-quality content, increasing defect discovery 60%.",
    ],
    technical_skills="Languages: Python, C++, SQL\nML/AI: Ranking, Retrieval, LLMs, NLP, Model Evaluation, Feature Engineering, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, TensorFlow, Hugging Face, FAISS, OpenSearch\nResearch: First-Author EMNLP 2025, Embeddings\nCloud and Systems: AWS, Spark, Docker, Kubernetes, Distributed Systems",
    must_haves=["ranking|retrieval", "llm", "nlp", "model|models", "python",
                "evaluation", "machine learning|ml", "pytorch"],
)
P[36] = dict(  # ByteDance  ML Graduate E-Commerce Governance BS/MS
    summary="Machine Learning Engineer at Amazon Prime Video building production ranking, retrieval, and LLM models for systems serving 1M+ users; first-author EMNLP 2025 researcher skilled in model development, evaluation, and scalable ML pipelines.",
    top_bullets=[
        "Built production ranking and retrieval models (FAISS + NDCG) serving 1M+ users at 0.5s end-to-end latency, lifting CTR 16% via iterative offline and online evaluation.",
        "Engineered an LLM-as-judge evaluation framework over 50K+ conversations daily with automated fact validation, increasing defect discovery 60% with actionable triage insights.",
    ],
    technical_skills="Languages: Python, C++, SQL\nML/AI: Ranking, Retrieval, LLMs, NLP, Model Evaluation, Feature Engineering, Fine-tuning (LoRA/PEFT)\nFrameworks: PyTorch, TensorFlow, Hugging Face, FAISS, OpenSearch\nResearch: First-Author EMNLP 2025, Embeddings\nCloud and Systems: AWS, Spark, Docker, Kubernetes, Distributed Systems",
    must_haves=["ranking|retrieval", "llm", "nlp", "model|models", "python",
                "evaluation", "machine learning|ml", "pytorch"],
)
P[37] = dict(  # Clarium  AI Engineer Data Intelligence (production Python+SQL, data quality)
    summary="Machine Learning Engineer at Amazon Prime Video building production AI systems and data pipelines for services serving 1M+ users; first-author EMNLP 2025 researcher with production Python and SQL and a track record of finding and fixing data-quality issues.",
    top_bullets=[
        "Built production Python and SQL data pipelines with automated validation that surfaced data-quality issues, increasing defect discovery 60% through an LLM-as-judge framework.",
        "Engineered retrieval and ranking pipelines (FAISS + NDCG) over large datasets serving 1M+ users at 0.5s latency, lifting CTR 16% via iterative evaluation.",
    ],
    technical_skills="Languages: Python, SQL\nAI/ML: LLM Integration, RAG, Retrieval, Embeddings, Model Evaluation, Data Quality\nData: Pandas, NumPy, Spark, Kafka, Airflow, PostgreSQL, NoSQL\nFrameworks: PyTorch, LangChain, FAISS, OpenSearch\nCloud and Systems: AWS, Docker, Kubernetes, Distributed Systems",
    must_haves=["python", "sql", "data quality|data", "production", "ai|llm",
                "pipeline|pipelines", "retrieval|evaluation"],
)
P[38] = dict(  # ByteDance  Grad Research Scientist DPU & AI Infra (systems, distributed, GPU for ML)
    summary="Machine Learning Engineer at Amazon Prime Video building production ML systems on distributed infrastructure serving 1M+ users; first-author EMNLP 2025 researcher combining ML research with low-latency distributed systems and inference optimization.",
    top_bullets=[
        "Built low-latency retrieval and ranking infrastructure (FAISS + NDCG) on distributed systems serving 1M+ users at 0.5s latency, lifting CTR 16% via iterative evaluation.",
        "Parallelized downstream and inference calls across distributed service boundaries, improving P99 latency 3x under peak load while researching scalable ML system design.",
    ],
    technical_skills="Languages: Python, C++, SQL\nSystems: Distributed Systems, Low-Latency Serving, Inference Optimization, Multithreading, Async Programming, Linux\nML/AI: LLMs, Retrieval, Ranking, Model Evaluation, GPU/Accelerated Inference\nFrameworks: PyTorch, FAISS, OpenSearch\nCloud and DevOps: AWS, Docker, Kubernetes, CI/CD",
    must_haves=["distributed systems|infrastructure", "low-latency|latency", "inference|serving",
                "python|c++", "ml|machine learning", "research", "optimization|parallel"],
)
P[39] = dict(  # JP Morgan  Data Scientist Associate (SQL+Python, data wrangling, KPIs, viz)
    summary="Machine Learning Engineer at Amazon Prime Video building production models and data pipelines for services serving 1M+ users; first-author EMNLP 2025 researcher skilled in Python and SQL data wrangling, KPI measurement, and communicating insights through visualization.",
    top_bullets=[
        "Built Python and SQL pipelines integrating multiple data sources into cohesive datasets for 1M+ users, defining KPIs and measurement frameworks that lifted engagement 30%.",
        "Analyzed large, complex datasets to extract insights and communicated findings through clear data visualizations, building an LLM-as-judge framework that raised defect discovery 60%.",
    ],
    technical_skills="Languages: Python, SQL\nData Science: Data Wrangling, KPIs, Measurement Frameworks, Data Visualization, Statistical Analysis\nML/AI: Machine Learning, Model Evaluation, NLP, XGBoost\nData: Pandas, NumPy, Spark, Airflow, PostgreSQL\nCloud: AWS, Azure (Databricks)",
    must_haves=["python", "sql", "data wrangling|data", "kpi|kpis|measurement", "visualization",
                "analysis|insights", "model|machine learning"],
)

# ---- assemble keyed by URL ------------------------------------------------- #
out = {}
for i, role in enumerate(sel):
    patch = P[i]
    assert patch, f"missing patch {i}"
    patch = dict(patch)
    patch["experience_section_index"] = 0
    out[role["url"]] = patch

pathlib.Path("data/_patches.json").write_text(json.dumps(out, indent=2))
print(f"wrote {len(out)} patches -> data/_patches.json")
