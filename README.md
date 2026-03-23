# Car Carer

> **English** | [Francais](README.fr.md) | [Deutsch](README.de.md) | [Espanol](README.es.md)

**Your AI-powered car maintenance companion**

[![CI](https://github.com/Greal-dev/car-carer/actions/workflows/ci.yml/badge.svg)](https://github.com/Greal-dev/car-carer/actions)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
[![GitHub Release](https://img.shields.io/github/v/release/Greal-dev/car-carer)](https://github.com/Greal-dev/car-carer/releases)

---

## What is Car Carer?

Car Carer is a self-hosted web application that keeps track of your car maintenance history. Upload your invoices, quotes, and inspection reports (PDF or photo) and let AI extract structured data automatically. Then use the intelligent chat assistant to ask questions about your car's history -- "When did I last change the brake pads?", "Compare my last two inspections", "How much did I spend on tires this year?".

## Features

- :page_facing_up: **AI document extraction** -- Upload a PDF or snap a photo; Gemini Flash 2.0 (via OpenRouter) extracts dates, costs, parts, mileage, and more
- :robot: **Intelligent chat assistant** -- Claude Sonnet 4 with 6 specialized tools queries your data and provides expert maintenance advice
- :car: **Multi-vehicle management** -- Track multiple vehicles with computed stats (mileage, spending, document count, health)
- :zap: **Batch upload** -- Import 50+ documents at once with real-time SSE progress tracking (8 concurrent extractions)
- :sparkles: **Vehicle auto-enrichment** -- Brand, model, plate number, VIN, and fuel type are automatically filled from uploaded documents
- :wrench: **Maintenance reminders & alerts** -- CT comparison detects new defects, severity changes, and anomalies
- :page_with_curl: **PDF export** -- Generate vehicle maintenance reports
- :iphone: **PWA** -- Installable on mobile, with camera capture for snapping invoices on the go
- :hammer: **No build step** -- Frontend uses Alpine.js + Tailwind CSS via CDN, zero configuration

## Screenshots

| Dashboard | Document Upload |
|:---------:|:---------------:|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Upload](docs/screenshots/upload.png) |

| AI Chat | Fuel Tracking |
|:-------:|:-------------:|
| ![Chat](docs/screenshots/chat.png) | ![Fuel](docs/screenshots/fuel.png) |

| Taxes & Insurance | Vehicle Sharing |
|:-----------------:|:---------------:|
| ![Taxes](docs/screenshots/taxes.png) | ![Sharing](docs/screenshots/sharing.png) |

## Quick Start

### Option A: Docker (recommended)

```bash
git clone https://github.com/Greal-dev/car-carer.git
cd car-carer
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

Open **http://localhost:8200** — done.

### Option B: Manual install

#### 1. Clone the repository

```bash
git clone https://github.com/Greal-dev/car-carer.git
cd car-carer
```

#### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 4. Run the application

```bash
python run.py
```

The app starts on **http://localhost:8200**. The SQLite database and uploads directory are created automatically on first run.

## Configuration

All configuration is done through the `.env` file. Only two variables are required:

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | -- | Anthropic API key for the chat agent (Claude Sonnet 4) |
| `OPENROUTER_API_KEY` | Yes | -- | OpenRouter API key for document extraction (Gemini Flash 2.0) |
| `DATABASE_URL` | No | `sqlite:///./care.db` | Database connection URL |
| `UPLOAD_DIR` | No | `./uploads` | Directory for uploaded files |
| `JWT_EXPIRE_HOURS` | No | `72` | JWT token expiration (hours) |
| `BATCH_MAX_CONCURRENT` | No | `3` | Max concurrent batch extractions |
| `BATCH_MAX_FILES` | No | `100` | Max files per batch upload |
| `EXTRACTION_TIMEOUT` | No | `60` | Extraction API timeout (seconds) |
| `EXTRACTION_MODEL` | No | `google/gemini-2.5-flash` | OpenRouter model for extraction |
| `MAX_PHOTO_SIZE_MB` | No | `10` | Max photo file size (MB) |

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Backend | **FastAPI** + Uvicorn | REST API with async support |
| Database | **SQLite** + SQLAlchemy | 8 tables, zero configuration |
| Chat AI | **Claude Sonnet 4** (Anthropic SDK) | Agentic chat with 6 tools |
| Extraction AI | **Gemini Flash 2.0** (OpenRouter) | Multimodal document extraction |
| PDF Processing | **PyMuPDF** | PDF to image conversion (200 DPI) |
| Image Processing | **Pillow** | EXIF correction, contrast, sharpening |
| Frontend | **Alpine.js** 3 + **Tailwind CSS** | Reactive SPA, no build step |
| PWA | Service Worker + Manifest | Installable, camera capture, offline assets |

## Project Structure

```
care-of-your-car/
├── run.py                      # Entry point (uvicorn)
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── care.db                     # SQLite database (auto-created)
├── uploads/                    # Uploaded files (auto-created)
├── app/
│   ├── main.py                 # FastAPI app, route mounting
│   ├── config.py               # Pydantic settings from .env
│   ├── database.py             # SQLAlchemy engine & session
│   ├── models/
│   │   ├── vehicle.py          # Vehicle model
│   │   ├── document.py         # Document model
│   │   ├── maintenance.py      # MaintenanceEvent + MaintenanceItem
│   │   ├── ct_report.py        # CTReport + CTDefect
│   │   └── conversation.py     # Conversation + Message
│   ├── schemas/                # Pydantic request/response schemas
│   ├── routers/
│   │   ├── vehicles.py         # CRUD vehicles + computed stats
│   │   ├── documents.py        # Upload, batch, SSE, extraction
│   │   └── chat.py             # Chat messages & conversations
│   ├── services/
│   │   ├── extraction.py       # Gemini pipeline: PDF/image → structured data
│   │   └── agent.py            # Claude agentic loop with tools
│   ├── agent/
│   │   ├── prompts.py          # System prompt for the assistant
│   │   └── tools.py            # 6 tools + dispatcher
│   └── static/
│       ├── index.html          # SPA (Alpine.js)
│       ├── manifest.json       # PWA manifest
│       ├── sw.js               # Service Worker
│       ├── css/style.css       # Custom styles
│       ├── js/app.js           # Alpine.js app logic
│       └── icons/              # PWA icons (192x192, 512x512)
```

## API Documentation

FastAPI auto-generates interactive API documentation. Once the app is running, visit:

- **Swagger UI**: [http://localhost:8200/docs](http://localhost:8200/docs)
- **ReDoc**: [http://localhost:8200/redoc](http://localhost:8200/redoc)

### Key endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/vehicles` | List all vehicles with computed stats |
| `POST` | `/api/vehicles` | Create a vehicle (only `name` required) |
| `POST` | `/api/documents/upload` | Upload & extract a single document |
| `POST` | `/api/documents/batch-upload` | Batch upload with SSE progress |
| `POST` | `/api/chat` | Send a message to the AI assistant |
| `GET` | `/api/chat/conversations` | List chat conversations |

## Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes** and add tests if applicable
4. **Commit** with a clear message: `git commit -m "Add my feature"`
5. **Push** to your fork: `git push origin feature/my-feature`
6. **Open a Pull Request** with a description of your changes

Please make sure your code follows the existing style and that the application still runs correctly.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

Built with:

- [Claude](https://www.anthropic.com/) by Anthropic -- powers the intelligent chat assistant
- [Gemini](https://deepmind.google/technologies/gemini/) by Google (via [OpenRouter](https://openrouter.ai/)) -- powers document extraction
- [FastAPI](https://fastapi.tiangolo.com/) -- the web framework
- [Alpine.js](https://alpinejs.dev/) -- lightweight reactive frontend
- [Tailwind CSS](https://tailwindcss.com/) -- utility-first CSS
