# ================================================================
# Reputation Intelligence — Frontend Dockerfile (React + Vite)
# ================================================================

FROM node:20-alpine AS base
WORKDIR /app
ENV NODE_ENV=development

# ─── Dependencies ────────────────────────────────────────────────
FROM base AS dependencies
COPY package*.json ./
RUN npm ci

# ─── Development ─────────────────────────────────────────────────
FROM dependencies AS development
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ─── Build ───────────────────────────────────────────────────────
FROM dependencies AS builder
ENV NODE_ENV=production
COPY . .
RUN npm run build

# ─── Production (nginx) ──────────────────────────────────────────
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
