# Models, components and assistance

Author: Enosh. OpenAI Codex assisted implementation, debugging, research, documentation and verification. Commits use Enosh's identity without a bot coauthor. This is a sanitized source snapshot of a continuing shop project; private operational history and real supplier records are excluded.

Python/FastAPI/Pydantic, PostgreSQL, SQLAlchemy 2, Alembic, PydanticAI, Anthropic client and Azure Document Intelligence SDK are recorded in the backend manifests/locks. Actual provider checks used the existing Azure-hosted Claude Sonnet 4.6 deployment and Document Intelligence prebuilt invoice extraction. Reviewers supply their own authorized endpoints and keys; no service access is bundled.

Frontend: React/TypeScript/Vite, Tailwind, shadcn/ui/Radix, Lucide, Geist, Prettier, react-markdown and remark-gfm. The Markdown renderer parses headings/lists/tables; raw HTML and embedded images are disabled. Dependency versions are locked. Generated shadcn code retains its MIT notice in frontend/THIRD_PARTY_NOTICES.md; installed dependencies retain their licenses.

The invoice-review tutorial/repository and Dave Ebbelaar's automation material informed concepts, not copied application code. ERPNext, Medusa, n8n, LangGraph, OpenHands and Temporal informed architectural research; their platforms were not embedded. Additional models are not benchmarked or claimed as integrated.

Light/dark automotive references informed independently written styling. Cabin photographs were generated with an AI image tool and are decorative, brand-neutral images. No proprietary automotive logos/fonts or tutorial proposal PDFs are redistributed.
