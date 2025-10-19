# Deployment Guide

Deploy the Doc2MD frontend to various platforms.

## Prerequisites

- A running Doc2MD API backend
- Node.js 18+ installed
- Git repository (for most platforms)

## Platform-Specific Guides

### Vercel (Recommended)

Vercel is the recommended platform as it's made by the Next.js team.

1. **Push code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Import to Vercel**
   - Go to [vercel.com](https://vercel.com)
   - Click "Import Project"
   - Select your GitHub repository
   - Configure:
     - Framework Preset: Next.js
     - Build Command: `npm run build`
     - Output Directory: `.next`

3. **Environment Variables**
   Add in Vercel dashboard:
   ```
   NEXT_PUBLIC_API_URL=https://your-api-domain.com
   ```

4. **Deploy**
   - Click "Deploy"
   - Your app will be live at `https://your-app.vercel.app`

### Netlify

1. **Create `netlify.toml`**
   ```toml
   [build]
     command = "npm run build"
     publish = ".next"

   [[plugins]]
     package = "@netlify/plugin-nextjs"
   ```

2. **Push to Git** and connect to Netlify

3. **Environment Variables**
   ```
   NEXT_PUBLIC_API_URL=https://your-api-domain.com
   ```

4. **Deploy**

### Docker

1. **Create `Dockerfile`**
   ```dockerfile
   FROM node:18-alpine AS deps
   WORKDIR /app
   COPY package*.json ./
   RUN npm ci

   FROM node:18-alpine AS builder
   WORKDIR /app
   COPY --from=deps /app/node_modules ./node_modules
   COPY . .
   ENV NEXT_TELEMETRY_DISABLED 1
   RUN npm run build

   FROM node:18-alpine AS runner
   WORKDIR /app
   ENV NODE_ENV production
   ENV NEXT_TELEMETRY_DISABLED 1

   RUN addgroup --system --gid 1001 nodejs
   RUN adduser --system --uid 1001 nextjs

   COPY --from=builder /app/public ./public
   COPY --from=builder /app/.next/standalone ./
   COPY --from=builder /app/.next/static ./.next/static

   USER nextjs
   EXPOSE 3000
   ENV PORT 3000

   CMD ["node", "server.js"]
   ```

2. **Update `next.config.ts`**
   ```typescript
   const nextConfig: NextConfig = {
     output: 'standalone',
   };
   ```

3. **Build and Run**
   ```bash
   docker build -t doc2md-front .
   docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://api:8080 doc2md-front
   ```

### Docker Compose (Full Stack)

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8080
    depends_on:
      - api

  api:
    image: doc2md-api:latest
    ports:
      - "8080:8080"
```

Run:
```bash
docker-compose up -d
```

### VPS/Traditional Hosting

1. **SSH into your server**

2. **Install Node.js and npm**
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
   sudo apt-get install -y nodejs
   ```

3. **Clone repository**
   ```bash
   git clone <your-repo-url>
   cd doc2md_front
   ```

4. **Install dependencies**
   ```bash
   npm ci --production
   ```

5. **Build**
   ```bash
   npm run build
   ```

6. **Set up PM2**
   ```bash
   npm install -g pm2
   pm2 start npm --name "doc2md-front" -- start
   pm2 save
   pm2 startup
   ```

7. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

8. **SSL with Let's Encrypt**
   ```bash
   sudo apt-get install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

## Environment Variables

Make sure to set these in your deployment platform:

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Doc2MD API URL | `https://api.doc2md.com` |

## CORS Configuration

Ensure your API backend allows requests from your frontend domain:

```python
# In your API's CORS configuration
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://your-frontend-domain.com",
]
```

## Health Checks

The frontend doesn't need a health check endpoint, but you can verify deployment:

```bash
curl https://your-domain.com
```

Should return the HTML for the Next.js app.

## Performance Optimization

### 1. Enable Compression
Most platforms enable this by default, but for self-hosted:
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
```

### 2. CDN (Optional)
- Use Cloudflare or similar for caching static assets
- Configure cache rules for `/static/*` and `/_next/static/*`

### 3. Image Optimization
If you add images later, use Next.js Image component:
```tsx
import Image from 'next/image'
<Image src="/logo.png" alt="Logo" width={200} height={50} />
```

## Monitoring

### Vercel Analytics
Add to your Vercel project for built-in analytics.

### Custom Monitoring
Use tools like:
- **Sentry** for error tracking
- **LogRocket** for session replay
- **Google Analytics** for usage stats

## Troubleshooting

### Build Fails
```bash
# Clear cache
rm -rf .next node_modules
npm install
npm run build
```

### API Connection Issues
- Check `NEXT_PUBLIC_API_URL` is correct
- Verify CORS settings on API
- Check network/firewall rules

### 404 on Page Refresh
- Ensure your hosting platform is configured for Next.js
- Vercel/Netlify handle this automatically
- For nginx, ensure proper proxy configuration

## Security Checklist

- [ ] HTTPS enabled
- [ ] Environment variables secured
- [ ] CORS properly configured
- [ ] No API keys in client code
- [ ] Content Security Policy configured
- [ ] Rate limiting on API

## Post-Deployment

1. Test all features:
   - Registration
   - Login
   - File upload
   - Job tracking
   - API key creation

2. Monitor logs for errors

3. Set up automated backups (if self-hosted)

4. Configure domain and SSL certificate

## Scaling

For high traffic:
- Use Vercel's automatic scaling
- Or set up load balancer with multiple instances
- Cache API responses where appropriate
- Consider Redis for session storage

## Support

If you encounter issues during deployment, check:
1. Build logs in your deployment platform
2. Browser console for client-side errors
3. API connectivity from deployment environment
4. CORS configuration on API server
