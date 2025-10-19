# Frontend multi-stage Dockerfile

# Build stage
FROM node:18-alpine as build
WORKDIR /app
ENV CI=true
# Some environments have the lockfile inside the nested `frontend/` folder (e.g. frontend/frontend/package-lock.json).
# Copy package.json and whichever lockfile exists into the build context.
COPY package.json ./
# Copy the full context (includes lockfiles located in the repo). This keeps the Dockerfile simple and avoids COPY failures.
COPY . ./
RUN npm install --legacy-peer-deps && npm run build

# Production stage
FROM nginx:stable-alpine
COPY --from=build /app/build /usr/share/nginx/html
# Copy custom nginx config if exists
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
