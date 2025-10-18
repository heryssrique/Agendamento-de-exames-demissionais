# Frontend multi-stage Dockerfile

# Build stage
FROM node:18-alpine as build
WORKDIR /app
ENV CI=true
COPY package.json package-lock.json ./
COPY . ./
RUN npm install --legacy-peer-deps && npm run build

# Production stage
FROM nginx:stable-alpine
COPY --from=build /app/build /usr/share/nginx/html
# Copy custom nginx config if exists
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
