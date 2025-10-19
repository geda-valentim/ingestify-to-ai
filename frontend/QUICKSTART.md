# Quick Start Guide

Get the Doc2MD frontend up and running in 5 minutes.

## Prerequisites

- Node.js 18+ installed
- Doc2MD API running at http://localhost:8080

## Installation & Setup

```bash
# 1. Install dependencies
npm install

# 2. Configure API URL (if different from default)
echo "NEXT_PUBLIC_API_URL=http://localhost:8080" > .env.local

# 3. Start development server
npm run dev
```

## First Steps

### 1. Open the App
Navigate to [http://localhost:3000](http://localhost:3000)

### 2. Create an Account
- Click "Sign up" or go to `/register`
- Enter email, username, password (min 6 characters)
- Submit and you'll be redirected to login

### 3. Login
- Enter your credentials
- You'll land on the dashboard

### 4. Upload Your First Document
- Drag & drop a PDF, DOCX, or other supported file
- Or click the upload area to browse
- Optionally add a custom name
- Click "Convert to Markdown"

### 5. Monitor the Job
- You'll be redirected to the job status page
- Watch the progress bar update in real-time
- For PDFs, see per-page progress
- When complete, view or download the Markdown

## API Key Setup (Optional)

For programmatic access:

1. Click "API Keys" in the dashboard
2. Click "Create API Key"
3. Enter a name (e.g., "My App")
4. Set expiration (default: 30 days)
5. Copy the key immediately (it's only shown once!)

Use in your code:
```bash
curl -X POST http://localhost:8080/upload \
  -H "X-API-Key: doc2md_sk_..." \
  -F "file=@document.pdf"
```

## Troubleshooting

### Can't connect to API
- Ensure the Doc2MD API is running at the configured URL
- Check `.env.local` has the correct `NEXT_PUBLIC_API_URL`
- Try accessing `http://localhost:8080/health` in your browser

### Build fails
```bash
# Clear cache and rebuild
rm -rf .next
npm run build
```

### Port 3000 already in use
```bash
# Use a different port
PORT=3001 npm run dev
```

## Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

## Next Steps

- Explore the job list page to see all your conversions
- Try searching for specific content in your documents
- Create multiple API keys for different environments
- Read the full [README.md](README.md) for detailed documentation

## Support

- Check the [README](README.md) for more details
- Report issues on GitHub
- Review the [OpenAPI spec](docs/doc2md_openapi.json) for API details
