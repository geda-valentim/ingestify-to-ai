# Doc2MD Frontend

A modern Next.js frontend for the Doc2MD API - Convert documents to Markdown with AI-powered processing.

## Features

- 🔐 **User Authentication** - Register, login with JWT tokens
- 📤 **Document Upload** - Drag & drop file upload with multiple format support
- 📊 **Real-time Job Tracking** - Monitor conversion progress with live updates
- 🔍 **Search & Filter** - Search jobs by content, filter by status
- 🔑 **API Key Management** - Create and manage API keys for programmatic access
- 📄 **Markdown Viewer** - Preview and download converted Markdown
- 🎨 **Modern UI** - Built with Tailwind CSS and shadcn/ui components

## Tech Stack

- **Next.js 15** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - High-quality UI components
- **TanStack Query** - Data fetching and caching
- **Zustand** - State management
- **Axios** - HTTP client
- **date-fns** - Date formatting

## Getting Started

### Prerequisites

- Node.js 24 LTS
- npm or pnpm
- Doc2MD API running (default: http://localhost:8080)

### Installation

1. Clone the repository:
```bash
cd doc2md_front
```

2. Install dependencies:
```bash
npm ci
```

3. Configure environment variables:
```bash
cp .env.example .env.local
```

Edit `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8080
```

4. Run the development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000) in your browser

## Project Structure

```
doc2md_front/
├── app/                    # Next.js app directory
│   ├── login/             # Login page
│   ├── register/          # Registration page
│   ├── dashboard/         # Main dashboard
│   ├── jobs/              # Job listing and detail pages
│   │   └── [id]/         # Individual job status page
│   ├── api-keys/          # API key management
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page (redirects)
│   └── providers.tsx      # React Query provider
├── components/            # React components
│   ├── ui/               # shadcn/ui components
│   ├── auth/             # Authentication components
│   ├── upload/           # File upload components
│   ├── jobs/             # Job-related components
│   └── markdown/         # Markdown viewer
├── lib/                   # Utilities and libraries
│   ├── api/              # API client and endpoints
│   │   ├── client.ts     # Axios client with auth
│   │   ├── auth.ts       # Auth endpoints
│   │   ├── apikeys.ts    # API key endpoints
│   │   └── jobs.ts       # Job endpoints
│   ├── store/            # Zustand stores
│   │   └── auth.ts       # Auth state management
│   └── utils.ts          # Utility functions
├── types/                 # TypeScript types
│   └── api.ts            # API types from OpenAPI spec
└── docs/                  # Documentation
    └── doc2md_openapi.json # OpenAPI specification
```

## Available Scripts

- `npm run dev` - Start development server with Turbopack
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run typecheck` - Check TypeScript

## Usage

### 1. Register an Account

- Navigate to `/register`
- Enter email, username, and password (min 6 characters)
- Submit to create your account

### 2. Login

- Navigate to `/login`
- Enter username/email and password
- You'll be redirected to the dashboard

### 3. Upload a Document

- Click the upload area or drag & drop a file
- Supported formats: PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT
- Optionally provide a custom name
- Click "Convert to Markdown"

### 4. Monitor Progress

- You'll be redirected to the job status page
- Watch real-time progress updates
- For PDFs, see per-page progress
- View or download the Markdown when complete

### 5. Manage Jobs

- Click "My Jobs" to see all conversions
- Filter by status (queued, processing, completed, failed)
- Search jobs by content
- Click any job to view details

### 6. Create API Keys

- Click "API Keys" in the dashboard
- Create a new key with a name and expiration
- Copy the key immediately (shown only once)
- Use in API requests with `X-API-Key` header

## API Integration

The frontend integrates with the Doc2MD API documented in `docs/doc2md_openapi.json`.

### Authentication

Two methods are supported:

1. **JWT Token** (for web UI):
   - Obtained via `/auth/login`
   - Stored in localStorage
   - Sent as `Authorization: Bearer <token>`

2. **API Key** (for programmatic access):
   - Created via `/api-keys/`
   - Sent as `X-API-Key: <key>`

### Polling Strategy

The app uses TanStack Query to poll for updates:

- Job status: Every 3 seconds while processing
- Job pages: Every 3 seconds until all complete
- Job list: Every 10 seconds
- Polling stops when job is completed or failed

## Supported Document Formats

- **PDF** - Portable Document Format
- **DOCX/DOC** - Microsoft Word
- **HTML** - Web pages
- **PPTX** - Microsoft PowerPoint
- **XLSX** - Microsoft Excel
- **RTF** - Rich Text Format
- **ODT** - OpenDocument Text

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Doc2MD API base URL | `http://localhost:8080` |

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

ISC

## Support

For issues or questions, please open an issue on the GitHub repository.
